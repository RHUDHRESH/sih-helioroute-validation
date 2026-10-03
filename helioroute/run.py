"""One command: execute tests, scenarios, logs, provenance, and real result plots."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import unittest

from .model import POLICIES, audit, dispatch
from .scenarios import load_scenarios

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_hashes():
    paths = [p for p in ROOT.rglob('*') if p.is_file() and
             (p.suffix in ('.py','.html','.js','.css','.yml','.yaml','.ps1') or p.name in ('experiments.json', 'requirements.lock', 'README.md', 'run.sh','serve.sh','.gitignore','.gitattributes')
              or (p.parent.name == 'docs' and p.suffix == '.md'))
             and not any(part in {'results', '.venv', '.git', '.playwright-cli', 'output', '__pycache__'} for part in p.relative_to(ROOT).parts)]
    entries = {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}
    return entries, hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def summarize(rows, dt_s):
    energies = {key[:-2]+'_wh': sum(row[key] for row in rows)*dt_s/3600
                for key in rows[0] if key.endswith('_w') and not key.endswith('signed_w')
                and key != 'balance_residual_w'}
    available = energies['total_available_pv_wh']
    used = energies['total_pv_used_raw_wh']
    renewable = energies['total_renewable_served_wh']
    required = energies['total_demand_wh']
    residual = (energies['total_available_pv_wh']+energies['total_grid_import_wh']
                -energies['total_served_wh']-energies['total_curtailment_wh']
                -energies['total_loss_wh']-energies['auxiliary_grid_wh'])
    metrics = []
    for name, numerator, denominator, unit in (
        ('pv_capture_fraction', used, available, 'fraction'),
        ('pv_to_useful_fraction', renewable, available, 'fraction'),
        ('useful_service_fraction', energies['total_served_wh'], required, 'fraction')):
        metrics.append({'metric': name, 'numerator': numerator, 'denominator': denominator,
                        'estimate': numerator/denominator if denominator > 0 else None, 'unit': unit,
                        'confidence_interval': None,
                        'status': 'pass' if denominator > 0 else 'not-applicable',
                        'reason': 'Deterministic synthetic case; no statistical CI' if denominator > 0 else 'Zero denominator'})
    return {'energy_wh': energies, 'metrics': metrics,
            'useful_service_status': 'pass' if energies['total_unmet_wh'] <= 1e-7 else 'fail',
            'system_service_status': 'pass' if all(r['service_status'] == 'met' for r in rows) else 'fail',
            'policy_shortfall_step_count': sum(r['service_status'] != 'met' for r in rows),
            'physical_infeasibility_proven_step_count': sum(r['physical_infeasibility_proven'] for r in rows),
            'peak_grid_import_w': max(r['total_grid_import_w'] for r in rows),
            'max_abs_step_balance_residual_w': max(abs(r['balance_residual_w']) for r in rows),
            'whole_run_balance_residual_wh': residual,
            'accounting_status': 'pass' if abs(residual) <= 1e-7 else 'fail'}


def paired(base, candidate, comparison):
    b, c = base['energy_wh'], candidate['energy_wh']
    same_demand = abs(b['total_demand_wh']-c['total_demand_wh']) <= 1e-7
    same_pv = abs(b['total_available_pv_wh']-c['total_available_pv_wh']) <= 1e-7
    same_trace = bool(base.get('input_trace_sha256')) and base.get('input_trace_sha256') == candidate.get('input_trace_sha256')
    feasible = (base['system_service_status'] == candidate['system_service_status'] == 'pass'
                and same_demand and same_pv and same_trace)
    grid_delta = b['total_grid_import_wh']-c['total_grid_import_wh']
    return {'comparison': comparison, 'status': 'pass' if feasible else 'fail',
            'reason': 'Identical input/useful-demand trace and full required service' if feasible else
                      'Input/service mismatch or policy service shortfall; grid savings claim invalid',
            'same_required_demand': same_demand, 'same_available_pv': same_pv, 'same_input_trace': same_trace,
            'raw_grid_difference_wh': grid_delta,
            'valid_grid_saving_wh': grid_delta if feasible else None,
            'grid_saving_fraction': grid_delta/b['total_grid_import_wh'] if feasible and b['total_grid_import_wh'] > 0 else None,
            'unmet_difference_wh': b['total_unmet_wh']-c['total_unmet_wh'],
            'confidence_interval': None, 'evidence_label': 'synthetic-dispatch-simulation'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT/'config/experiments.json'))
    parser.add_argument('--output', default=str(ROOT/'results/latest'))
    parser.add_argument('--no-plots', action='store_true', help='Core stdlib-only run; report plots as not-run')
    args = parser.parse_args()
    os.chdir(ROOT)
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = io.StringIO()
    tests = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
    (output/'test_report.txt').write_text(log.getvalue())
    test_summary = {'status': 'pass' if tests.wasSuccessful() else 'fail', 'tests_run': tests.testsRun,
                    'failures': len(tests.failures), 'errors': len(tests.errors), 'skipped': len(tests.skipped)}
    dump(output/'test_summary.json', test_summary)
    if not tests.wasSuccessful():
        print(log.getvalue())
        raise SystemExit('Tests failed; no favorable summary will be generated')
    config, scenarios = load_scenarios(config_path)
    inputs, outputs, scenario_results = [], [], []
    for spec, params, steps in scenarios:
        common = []
        for index, step in enumerate(steps):
            item = {'schema_version':1,'scenario': spec['id'], 'step_index': index, 'time_s': index*spec['dt_s'],
                    'dt_s': spec['dt_s'], **asdict(step)}
            common.append(item)
            inputs.append(item)
        variant_results = {}
        for policy in POLICIES:
            rows = []
            for item, step in zip(common, steps):
                row = dispatch(step, params, policy)
                problems = audit(step, params, row)
                if problems:
                    raise RuntimeError(f"{spec['id']} {policy} {item['step_index']}: {problems}")
                rows.append(row)
                outputs.append({**{k:item[k] for k in ('schema_version','scenario','step_index','time_s','dt_s')}, **row})
            variant_results[policy] = summarize(rows, spec['dt_s'])
            variant_results[policy]['input_trace_sha256'] = hashlib.sha256(json.dumps(common,sort_keys=True).encode()).hexdigest()
        scenario_results.append({'scenario': spec['id'], 'description': spec['description'],
                                 'parameters': asdict(params), 'n_steps': len(steps), 'dt_s': spec['dt_s'],
                                 'variants': variant_results,
                                 'comparison_A_hardware': paired(variant_results['conventional'], variant_results['routed_restricted_optimizer'], 'conventional vs added-link topology; local-first restriction in both'),
                                 'comparison_B_controller': paired(variant_results['routed_greedy'], variant_results['routed_restricted_optimizer'], 'loss-aware greedy vs restricted surplus-sharing optimizer; identical hardware'),
                                 'fixed_order_ablations': ['routed_existing_first', 'routed_link_first']})
    write_csv(output/'inputs.csv', inputs)
    write_csv(output/'dispatch.csv', outputs)
    shutil.copyfile(config_path, output/'experiment_config.json')
    summary = {'schema_version':1, 'evidence_label':config['evidence_label'],
               'evaluation_split':config['evaluation_split'], 'storage':'absent in every variant',
               'objective':'after fixed local-first allocation, maximize PV-surplus-derived useful service, then minimize source draw, then added-link use',
               'optimizer_scope':'restricted surplus-sharing optimizer; not global service allocation under binding grid caps',
               'uncertainty':'No physical calibration, statistical CI, or held-out generalization evidence',
               'test_summary':test_summary, 'scenario_count':len(scenarios), 'dispatch_rows':len(outputs),
               'scenario_results':scenario_results}
    dump(output/'summary.json', summary)
    dump(output/'replay.json', {'schema_version':1,'evidence_label':config['evidence_label'],'inputs':inputs,
                               'rows':outputs,'scenarios':scenario_results})
    entries, tree_hash = source_hashes()
    manifest = {'schema_version':1,'run_id': 'synthetic-'+tree_hash[:12]+'-'+sha(config_path)[:8],
                'generated_at_utc':datetime.now(timezone.utc).isoformat(),
                'evidence_label':config['evidence_label'], 'seed':config['seed'],
                'property_test_seed':160289, 'exhaustive_test_seed':62017,
                'source_tree_sha256':tree_hash, 'source_files_sha256':entries,
                'configuration_sha256':sha(config_path), 'input_trace_sha256':sha(output/'inputs.csv'),
                'dependency_lock_sha256':sha(ROOT/'requirements.lock'),
                'python':sys.version, 'platform':platform.platform(), 'machine':platform.machine(),
                'processor':platform.processor() or 'not reported',
                'baseline_id':'conventional', 'policies':list(POLICIES),
                'units':{'power':'W average over step','energy':'Wh','time':'s'},
                'runtime_dependencies':{}, 'plot_status':'not-run' if args.no_plots else 'pending',
                'algorithm':'restricted surplus-sharing optimizer via exact 2D vertex enumeration; fixed local-first allocation; no external solver or forecast',
                'solver_tolerance_w':1e-8, 'per_step_audit_tolerance_w':1e-7,
                'whole_run_audit_tolerance_wh':1e-7,
                'synthetic_data_license':'project-created deterministic synthetic fixtures; no external dataset',
                'model_hash':None, 'model_hash_reason':'No trained model or physical plant model'}
    dump(output/'manifest.json', manifest)
    verification = subprocess.run([sys.executable, str(ROOT/'verify_artifacts.py'), str(output)], capture_output=True, text=True)
    (output/'artifact_verification.txt').write_text(verification.stdout+verification.stderr)
    if verification.returncode:
        raise SystemExit(verification.stdout+verification.stderr)
    node = shutil.which('node')
    if node:
        viewer_test = subprocess.run([node,str(ROOT/'tests/test_viewer.js'),str(output)],capture_output=True,text=True)
        (output/'viewer_logic_tests.json').write_text(viewer_test.stdout if viewer_test.returncode==0 else viewer_test.stdout+viewer_test.stderr)
        if viewer_test.returncode:
            raise SystemExit(viewer_test.stdout+viewer_test.stderr)
        manifest['viewer_logic_test_status']='pass'
        manifest['node']=subprocess.run([node,'--version'],capture_output=True,text=True,check=True).stdout.strip()
    else:
        dump(output/'viewer_logic_tests.json',{'status':'not-run','reason':'Node.js not installed; Python simulation and audit still ran'})
        manifest['viewer_logic_test_status']='not-run'
    manifest['browser_visual_qa_status']='not-run'
    manifest['browser_visual_qa_reason']='The reproduction command does not launch a browser; separate local browser smoke evidence is recorded in docs/BROWSER_QA.md'
    if not args.no_plots:
        from .plots import make_plots
        make_plots(output)
        manifest['plot_status'] = 'pass'
        manifest['runtime_dependencies'] = {name:version(name) for name in ('matplotlib','numpy')}
    dump(output/'manifest.json', manifest)
    hashes = {str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact_hashes.json'}
    dump(output/'artifact_hashes.json', hashes)
    print(json.dumps({'output':str(output), 'tests':test_summary, 'scenarios':len(scenarios),
                      'dispatch_rows':len(outputs), 'independent_csv_audit':'pass',
                      'plots':manifest['plot_status'], 'run_id':manifest['run_id']}, indent=2))


if __name__ == '__main__':
    main()
