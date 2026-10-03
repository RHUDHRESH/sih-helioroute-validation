#!/usr/bin/env python3
"""Independent CSV evaluator: deliberately imports no helioroute code.

Rebuilds the node/global ledger, checks both-end real-power ratings, grid caps,
service, failure behavior, paired policy rows, and every reported energy total.
It is a software accounting check, not a physical simulator or safety proof.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

TOL = 1e-7
POLICIES = ('conventional','routed_greedy','routed_restricted_optimizer','routed_existing_first','routed_link_first')


def verify(directory):
    directory = Path(directory)
    summary = json.loads((directory/'summary.json').read_text())
    scenarios = {s['scenario']: s for s in summary['scenario_results']}
    config = json.loads((directory/'experiment_config.json').read_text())
    configs = {s['id']: s for s in config['scenarios']}
    with (directory/'inputs.csv').open() as f:
        inputs_list = list(csv.DictReader(f))
    inputs = {(r['scenario'],int(r['step_index'])):r for r in inputs_list}
    with (directory/'dispatch.csv').open() as f:
        outputs = list(csv.DictReader(f))
    errors, seen, groups = [], set(), {}
    def check(ok, label):
        if not ok:
            errors.append(label)
    manifest=json.loads((directory/'manifest.json').read_text())
    check(summary.get('schema_version')==config.get('schema_version')==manifest.get('schema_version')==1,'unsupported artifact schema')
    for file_name,field in (('inputs.csv','input_trace_sha256'),('experiment_config.json','configuration_sha256')):
        actual_hash=hashlib.sha256((directory/file_name).read_bytes()).hexdigest()
        check(actual_hash==manifest[field],file_name+': manifest hash mismatch')
    for sid,spec in configs.items():
        if 'steps' not in spec:
            continue
        check(len([key for key in inputs if key[0]==sid])==len(spec['steps']),sid+': fixed config step count')
        for index,step in enumerate(spec['steps']):
            if (sid,index) not in inputs:
                check(False,sid+': missing configured input')
                continue
            configured={'grid_cap_a_w':1e9,'grid_cap_b_w':1e9,'link_available':True,'telemetry_fresh':True}|step
            actual=inputs[sid,index]
            for field,expected in configured.items():
                same=(actual[field]==str(expected)) if isinstance(expected,bool) else abs(float(actual[field])-expected)<=TOL
                check(same,sid+'/'+str(index)+': input differs from fixed configuration '+field)
    check(len(inputs) == len(inputs_list), 'duplicate input keys')
    check(len(outputs) == len(inputs)*len(POLICIES), 'missing or extra policy rows')
    largest = 0.
    for raw in outputs:
        sid, policy, index = raw['scenario'], raw['policy'], int(raw['step_index'])
        label = f'{sid}/{policy}/{index}'
        key = sid, index
        check(key in inputs and sid in scenarios and policy in POLICIES, label+': unknown key')
        if key not in inputs or sid not in scenarios or policy not in POLICIES:
            continue
        seenkey = sid, policy, index
        check(seenkey not in seen, label+': duplicate dispatch')
        seen.add(seenkey)
        original = inputs[key]
        check(raw.get('schema_version')==original.get('schema_version')=='1',label+': unsupported CSV schema')
        spec = configs[sid]
        p = config['default_parameters'] | spec.get('parameters', {})
        check(p == scenarios[sid]['parameters'], label+': summary changed parameters')
        w = {k:float(v) for k,v in raw.items() if k.endswith('_w')}
        for k,v in w.items():
            check(math.isfinite(v), label+': nonfinite '+k)
            if k not in ('conventional_signed_w','link_signed_w','balance_residual_w'):
                check(v >= -TOL, label+': negative '+k)
        dt, time = float(raw['dt_s']), float(raw['time_s'])
        check(dt == float(original['dt_s']) == spec['dt_s'], label+': interval mismatch')
        check(time == float(original['time_s']) == index*dt, label+': time mismatch')
        near = lambda a,b: abs(a-b) <= TOL
        direction = int(raw['direction'])
        check(direction in (-1,0,1), label+': direction')
        check(near(w['conventional_signed_w'], direction*w['conventional_send_w']), label+': conventional sign')
        check(near(w['link_signed_w'], direction*w['link_send_w']), label+': link sign')
        check(w['conventional_signed_w']*w['link_signed_w'] >= -TOL, label+': opposing flows')
        installed = policy != 'conventional'
        aux_request = p['auxiliary_standby_w'] if installed else 0.
        aux = min(aux_request,float(original['grid_cap_b_w']))
        enabled = (installed and original['link_available'] == 'True' and original['telemetry_fresh'] == 'True'
                   and aux_request-aux <= 1e-8)
        check(near(w['auxiliary_requested_w'],aux_request) and near(w['auxiliary_grid_w'],aux)
              and near(w['auxiliary_unmet_w'],aux_request-aux), label+': auxiliary ledger')
        check((raw['link_enabled'] == 'True') == enabled, label+': incorrect fallback enable')
        for name, eta, send_cap, receive_cap in (
            ('conventional',p['conventional_efficiency'],p['conventional_capacity_w'],p['conventional_receive_capacity_w']),
            ('link',p['link_efficiency'],p['link_capacity_w'] if enabled else 0.,p['link_receive_capacity_w'])):
            flow = w[name+'_send_w']
            check(flow <= send_cap+TOL and flow*eta <= receive_cap+TOL, label+': '+name+' rating')
            check(near(w[name+'_loss_w'],flow*(1-eta)), label+': '+name+' loss')
        incoming = w['conventional_send_w']*p['conventional_efficiency']+w['link_send_w']*p['link_efficiency']
        outgoing = w['conventional_send_w']+w['link_send_w']
        check(near(incoming,w['incoming_bus_a_w']+w['incoming_bus_b_w']),label+': incoming total')
        check(near(outgoing,w['outgoing_bus_a_w']+w['outgoing_bus_b_w']),label+': outgoing total')
        if direction == 1:
            check(near(w['outgoing_bus_a_w'],outgoing) and near(w['incoming_bus_b_w'],incoming), label+': A-to-B endpoints')
        elif direction == -1:
            check(near(w['outgoing_bus_b_w'],outgoing) and near(w['incoming_bus_a_w'],incoming), label+': B-to-A endpoints')
        else:
            check(near(outgoing,0),label+': zero-direction transfer')
        loss = w['conventional_loss_w']+w['link_loss_w']
        for node in ('a','b'):
            pv,demand = float(original['pv_'+node+'_w']),float(original['load_'+node+'_w'])
            val = lambda name: w[name+'_'+node+'_w']
            check(near(val('pv_available'),pv) and near(val('demand'),demand), label+': changed input '+node)
            check(val('pv_used_raw') <= pv+TOL, label+': source budget '+node)
            check(near(pv,val('pv_used_raw')+val('curtailment')),label+': PV ledger '+node)
            check(near(val('source_loss'),val('pv_used_raw')*(1-p['source_efficiency'])),label+': source loss '+node)
            check(near(val('load_loss'),val('load_bus')*(1-p['load_efficiency'])),label+': load loss '+node)
            check(near(val('pv_used_raw')-val('source_loss')+val('incoming_bus'),val('load_bus')+val('outgoing_bus')),label+': bus ledger '+node)
            check(near(val('load_bus')-val('load_loss'),val('renewable_served')),label+': load conversion '+node)
            check(near(val('renewable_served')+val('grid_import'),val('served')),label+': useful service '+node)
            check(near(demand,val('served')+val('unmet')),label+': unmet service '+node)
            check(val('grid_import')+(aux if node == 'b' else 0.) <= float(original['grid_cap_'+node+'_w'])+TOL,label+': grid rating '+node)
            loss += val('source_loss')+val('load_loss')
        for total, primitive in (('total_available_pv_w','pv_available'),('total_demand_w','demand'),
                                 ('total_pv_used_raw_w','pv_used_raw'),('total_renewable_served_w','renewable_served'),
                                 ('total_useful_grid_import_w','grid_import'),('total_served_w','served'),
                                 ('total_unmet_w','unmet'),('total_curtailment_w','curtailment'),
                                 ('total_source_loss_w','source_loss'),('total_load_loss_w','load_loss')):
            check(near(w[total],w[primitive+'_a_w']+w[primitive+'_b_w']),label+': '+total)
        check(near(w['total_grid_import_w'],w['total_useful_grid_import_w']+aux),label+': total grid')
        check(near(w['total_loss_w'],loss),label+': total loss')
        residual = (float(original['pv_a_w'])+float(original['pv_b_w'])+w['total_grid_import_w']
                    -w['served_a_w']-w['served_b_w']-w['curtailment_a_w']-w['curtailment_b_w']-loss-aux)
        largest = max(largest,abs(residual))
        check(abs(residual) <= TOL and near(residual,w['balance_residual_w']),label+': global ledger')
        feasible = w['unmet_a_w']+w['unmet_b_w']+aux_request-aux <= 1e-8
        check(raw['service_status'] == ('met' if feasible else 'policy_service_shortfall'),label+': feasibility flag')
        supply_bound=max(0.,float(original['load_a_w'])+float(original['load_b_w'])+aux_request
                         -float(original['pv_a_w'])-float(original['pv_b_w'])
                         -float(original['grid_cap_a_w'])-float(original['grid_cap_b_w']))
        check(near(w['supply_lower_bound_shortfall_w'],supply_bound),label+': supply bound')
        check((raw['physical_infeasibility_proven']=='True') == (supply_bound>1e-8),label+': unsupported physical infeasibility claim')
        groups.setdefault((sid,policy),[]).append((dt,w,raw['service_status']))
    for (sid,policy),rows in groups.items():
        report = scenarios[sid]['variants'][policy]
        check(len(rows) == scenarios[sid]['n_steps'],sid+'/'+policy+': missing steps')
        for name, reported in report['energy_wh'].items():
            key = name[:-3]+'_w'
            actual = sum(dt*w[key]/3600 for dt,w,_ in rows)
            check(abs(actual-reported) <= TOL,sid+'/'+policy+': incorrect summary '+name)
        check(report['system_service_status'] == ('pass' if all(s == 'met' for _,_,s in rows) else 'fail'),sid+'/'+policy+': summary status')
    for sid,s in scenarios.items():
        for policy in POLICIES:
            check((sid,policy) in groups,sid+': missing policy '+policy)
        for name, b, c in (('comparison_A_hardware','conventional','routed_restricted_optimizer'),
                           ('comparison_B_controller','routed_greedy','routed_restricted_optimizer')):
            result = s[name]
            base,candidate = s['variants'][b],s['variants'][c]
            valid = base['system_service_status'] == candidate['system_service_status'] == 'pass'
            valid = (valid and base['input_trace_sha256']==candidate['input_trace_sha256']
                     and abs(base['energy_wh']['total_demand_wh']-candidate['energy_wh']['total_demand_wh'])<=TOL
                     and abs(base['energy_wh']['total_available_pv_wh']-candidate['energy_wh']['total_available_pv_wh'])<=TOL)
            delta = base['energy_wh']['total_grid_import_wh']-candidate['energy_wh']['total_grid_import_wh']
            check(abs(result['raw_grid_difference_wh']-delta) <= TOL,sid+': paired delta')
            check(result['status'] == ('pass' if valid else 'fail'),sid+': paired status')
            check((result['valid_grid_saving_wh'] is not None) == valid,sid+': fabricated saving on infeasible service')
            if valid:
                check(abs(result['valid_grid_saving_wh']-delta) <= TOL,sid+': claimed saving')
        greedy,opt = s['variants']['routed_greedy']['energy_wh'],s['variants']['routed_restricted_optimizer']['energy_wh']
        check(abs(greedy['total_renewable_served_wh']-opt['total_renewable_served_wh']) <= TOL,sid+': greedy/optimizer expected equality')
    replay=json.loads((directory/'replay.json').read_text())
    check(replay.get('schema_version')==1,'unsupported replay schema')
    check(replay['scenarios']==summary['scenario_results'],'viewer replay summary differs from audited summary')
    check(len(replay['rows'])==len(outputs),'viewer replay row count differs')
    for plotted,raw in zip(replay['rows'],outputs):
        for key,value in plotted.items():
            if isinstance(value,bool):
                same=raw[key]==str(value)
            elif isinstance(value,(int,float)):
                same=abs(float(raw[key])-value)<=TOL
            else:
                same=raw[key]==value
            check(same,'viewer replay field differs from CSV: '+key)
    result = {'status':'fail' if errors else 'pass','checked_input_steps':len(inputs),
              'checked_dispatch_rows':len(outputs),'max_abs_recomputed_step_residual_w':largest,
              'absolute_tolerance_w_and_wh':TOL,'errors':errors}
    return result


if __name__ == '__main__':
    report = verify(sys.argv[1] if len(sys.argv)>1 else 'results/latest')
    print(json.dumps(report,indent=2,allow_nan=False))
    raise SystemExit(1 if report['errors'] else 0)
