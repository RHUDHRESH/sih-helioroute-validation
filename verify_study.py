"""Independent streamed audit; does not import the dispatch implementation."""
import csv
import gzip
import json
import math
from pathlib import Path
import sys

TOL = 1e-7
POLICIES = {'conventional', 'routed_greedy', 'routed_restricted_optimizer', 'routed_existing_first', 'routed_link_first'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(root):
    root = Path(root)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    sums, seen, rows, residual_max = {}, {}, 0, 0
    with gzip.open(root/'dispatch.jsonl.gz', 'rt', encoding='utf-8') as handle:
        for line in handle:
            item = json.loads(line)
            name, i, p, s = item['case'], item['index'], item['parameters'], item['input']
            require(i == seen.get(name, 0), f'{name}: duplicate or missing input step')
            seen[name] = i+1
            require(set(item['outputs']) == POLICIES, 'missing or extra policy')
            sums.setdefault(name, {policy: [0, 0, 0] for policy in POLICIES})
            for policy, r in item['outputs'].items():
                require(r['policy'] == policy, 'policy identity differs')
                for key, value in r.items():
                    if key.endswith('_w'):
                        require(math.isfinite(value), 'nonfinite output')
                        if key not in ('balance_residual_w', 'conventional_signed_w', 'link_signed_w'):
                            require(value >= -TOL, 'negative physical ledger field')
                aux = 0 if policy == 'conventional' else p['auxiliary_standby_w']
                aux_grid = min(aux, s['grid_cap_b_w'])
                enabled = policy != 'conventional' and s['link_available'] and s['telemetry_fresh'] and aux-aux_grid <= 1e-8
                require(r['link_enabled'] == enabled, 'incorrect fail-safe flag')
                require(r['link_send_w'] <= (p['link_capacity_w'] if enabled else 0)+TOL, 'link limit')
                require(r['link_send_w']*p['link_efficiency'] <= p['link_receive_capacity_w']+TOL, 'receiving link limit')
                require(r['conventional_send_w'] <= p['conventional_capacity_w']+TOL, 'existing path limit')
                require(r['conventional_send_w']*p['conventional_efficiency'] <= p['conventional_receive_capacity_w']+TOL, 'receiving existing limit')
                loss = r['conventional_send_w']*(1-p['conventional_efficiency'])+r['link_send_w']*(1-p['link_efficiency'])
                require(r['direction'] in (-1, 0, 1), 'invalid direction')
                for path, efficiency in [('conventional', p['conventional_efficiency']), ('link', p['link_efficiency'])]:
                    require(abs(r[f'{path}_signed_w']-r['direction']*r[f'{path}_send_w']) <= TOL, 'signed flow')
                    require(abs(r[f'{path}_loss_w']-r[f'{path}_send_w']*(1-efficiency)) <= TOL, 'path loss')
                sent = r['conventional_send_w']+r['link_send_w']
                received = r['conventional_send_w']*p['conventional_efficiency']+r['link_send_w']*p['link_efficiency']
                require(abs(r['outgoing_bus_a_w']+r['outgoing_bus_b_w']-sent) <= TOL, 'cross-feeder sending closure')
                require(abs(r['incoming_bus_a_w']+r['incoming_bus_b_w']-received) <= TOL, 'cross-feeder receiving closure')
                require((r['direction'] == 1 and r['outgoing_bus_b_w'] <= TOL and r['incoming_bus_a_w'] <= TOL) or
                        (r['direction'] == -1 and r['outgoing_bus_a_w'] <= TOL and r['incoming_bus_b_w'] <= TOL) or
                        (r['direction'] == 0 and sent <= TOL), 'direction closure')
                for node in ('a', 'b'):
                    raw, served, grid = r[f'pv_used_raw_{node}_w'], r[f'served_{node}_w'], r[f'grid_import_{node}_w']
                    incoming, outgoing, bus = r[f'incoming_bus_{node}_w'], r[f'outgoing_bus_{node}_w'], r[f'load_bus_{node}_w']
                    require(abs(raw*p['source_efficiency']+incoming-outgoing-bus) <= TOL, 'node bus closure')
                    require(abs(bus*p['load_efficiency']+grid-served) <= TOL, 'load closure')
                    require(abs(raw+r[f'curtailment_{node}_w']-s[f'pv_{node}_w']) <= TOL, 'PV closure')
                    require(abs(served+r[f'unmet_{node}_w']-s[f'load_{node}_w']) <= TOL, 'service closure')
                    require(grid+(aux_grid if node == 'b' else 0) <= s[f'grid_cap_{node}_w']+TOL, 'grid cap')
                    loss += raw*(1-p['source_efficiency'])+bus*(1-p['load_efficiency'])
                residual = s['pv_a_w']+s['pv_b_w']+r['grid_import_a_w']+r['grid_import_b_w']-r['served_a_w']-r['served_b_w']-r['curtailment_a_w']-r['curtailment_b_w']-loss
                require(abs(residual) <= TOL and abs(loss-r['total_loss_w']) <= TOL, 'energy ledger')
                require(abs(r['total_grid_import_w']-r['grid_import_a_w']-r['grid_import_b_w']-aux_grid) <= TOL, 'auxiliary accounting')
                require(abs(r['total_unmet_w']-r['unmet_a_w']-r['unmet_b_w']) <= TOL, 'unmet total')
                require(abs(r['auxiliary_unmet_w']-(aux-aux_grid)) <= TOL, 'auxiliary shortfall')
                sums[name][policy][0] += r['total_grid_import_w']*item['dt_s']/3600
                sums[name][policy][1] += r['total_unmet_w']*item['dt_s']/3600
                sums[name][policy][2] += r['auxiliary_unmet_w']*item['dt_s']/3600
                residual_max = max(residual_max, abs(residual))
                rows += 1
    with (root/'cases.csv').open(encoding='utf-8', newline='') as handle:
        records = list(csv.DictReader(handle))
    require(len(records) == len(sums) == manifest['case_count'], 'case count')
    require(len({r['case'] for r in records}) == len(records), 'duplicate summary case')
    for record in records:
        name = record['case']
        b, c, g = sums[name]['conventional'], sums[name]['routed_restricted_optimizer'], sums[name]['routed_greedy']
        require(int(record['steps']) == seen[name], 'summary steps')
        for key, value in [('baseline_grid_wh', b[0]), ('routed_grid_wh', c[0]), ('baseline_unmet_wh', b[1]), ('routed_unmet_wh', c[1]), ('routed_aux_unmet_wh', c[2]), ('raw_grid_delta_wh', b[0]-c[0]), ('controller_grid_delta_wh', g[0]-c[0])]:
            require(abs(float(record[key])-value) <= TOL, 'summary differs from raw dispatch')
        valid = b[1] <= TOL and c[1] <= TOL and c[2] <= TOL
        require((record['comparison_valid'] == 'True') == valid, 'invalid service comparison')
        require(bool(record['valid_grid_saving_wh']) == valid, 'saving falsely retained on shortfall')
        if valid:
            require(abs(float(record['valid_grid_saving_wh'])-(b[0]-c[0])) <= TOL, 'saving differs')
        require(abs(g[0]-c[0]) <= TOL, 'controller equality')
    require(rows == manifest['dispatches'] and sum(seen.values()) == manifest['input_steps'], 'manifest count')
    return {'status': 'pass', 'checked_cases': len(sums), 'checked_dispatches': rows, 'max_abs_residual_w': residual_max, 'tolerance': TOL}


if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1]), indent=2))
