"""Seeded full-day profiles, factorial sensitivities and capped-grid stress study."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import platform
import random
import sys

from helioroute.model import POLICIES, Parameters, Step, dispatch, audit
from helioroute.run import source_hashes
from verify_study import verify

ROOT = Path(__file__).resolve().parent
SEED = 2621703


def cases(days=100, trials=10000):
    rng = random.Random(SEED)
    for day in range(days):
        p = Parameters(source_efficiency=rng.uniform(.90, 1), load_efficiency=rng.uniform(.90, 1),
                       conventional_efficiency=rng.uniform(.9, 1), conventional_capacity_w=rng.uniform(0, 250),
                       conventional_receive_capacity_w=rng.uniform(10, 250), link_efficiency=rng.uniform(.75, 1),
                       link_capacity_w=rng.uniform(0, 200), link_receive_capacity_w=rng.uniform(10, 200),
                       auxiliary_standby_w=rng.choice([0, 1, 2, 5, 10]))
        peak_a, peak_b = rng.uniform(0, 600), rng.uniform(0, 600)
        load_a, load_b = rng.uniform(20, 200), rng.uniform(20, 200)
        daylight, shift = rng.uniform(8, 14), rng.uniform(-1, 1)
        steps = []
        for n in range(288):
            h = n / 12
            solar = max(0, math.sin(math.pi * (h - (12-daylight/2+shift)) / daylight)) if 12-daylight/2+shift <= h <= 12+daylight/2+shift else 0
            steps.append(Step(peak_a*solar*rng.uniform(.35, 1), peak_b*solar*rng.uniform(.35, 1),
                              load_a*rng.uniform(.6, 1.4), load_b*rng.uniform(.6, 1.4),
                              link_available=rng.random() > .05, telemetry_fresh=rng.random() > .05))
        yield f'day_{day:03}', 'seeded_day', p, 300, steps
    # 6 existing ratings x 6 link efficiencies x 6 standby loads = 216 cells.
    for cap, eta, standby in itertools.product([0, 10, 30, 50, 80, 200], [.75, .80, .85, .90, .95, 1], [0, 1, 2, 5, 10, 20]):
        p = Parameters(source_efficiency=1, load_efficiency=1, conventional_efficiency=1,
                       conventional_capacity_w=cap, link_efficiency=eta, link_capacity_w=50,
                       auxiliary_standby_w=standby)
        yield f'sensitivity_{cap}_{eta}_{standby}', 'factorial', p, 3600, [Step(100, 0, 20, 100)]
    for n in range(trials):
        p = Parameters(source_efficiency=rng.uniform(.5, 1), load_efficiency=rng.uniform(.5, 1),
                       conventional_efficiency=rng.uniform(.5, 1), conventional_capacity_w=rng.uniform(0, 500),
                       conventional_receive_capacity_w=rng.uniform(0, 500), link_efficiency=rng.uniform(.5, 1),
                       link_capacity_w=rng.uniform(0, 500), link_receive_capacity_w=rng.uniform(0, 500),
                       auxiliary_standby_w=rng.uniform(0, 20))
        s = Step(*(rng.uniform(0, 1000) for _ in range(4)),
                 grid_cap_a_w=rng.choice([0, rng.uniform(0, 500), 1e9]),
                 grid_cap_b_w=rng.choice([0, rng.uniform(0, 500), 1e9]),
                 link_available=rng.random() > .1, telemetry_fresh=rng.random() > .1)
        yield f'stress_{n:05}', 'capped_grid_stress', p, 1, [s]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def run(out, days, trials):
    if out.exists():
        raise FileExistsError(f'Choose a fresh output directory: {out}')
    out.mkdir(parents=True)
    records, steps_count, rows_count = [], 0, 0
    with (out/'dispatch.jsonl.gz').open('wb') as binary:
        with gzip.GzipFile(fileobj=binary, mode='wb', mtime=0, filename='') as zipped:
            with io.TextIOWrapper(zipped, encoding='utf-8', newline='\n') as log:
                for name, group, p, dt, steps in cases(days, trials):
                    energy = {policy: {'grid': 0, 'unmet': 0, 'curtailment': 0, 'loss': 0, 'served': 0, 'aux_unmet': 0} for policy in POLICIES}
                    for index, s in enumerate(steps):
                        outputs = {policy: dispatch(s, p, policy) for policy in POLICIES}
                        for policy, row in outputs.items():
                            errors = audit(s, p, row)
                            if errors:
                                raise RuntimeError((name, index, policy, errors))
                            for metric, field in [('grid', 'total_grid_import_w'), ('unmet', 'total_unmet_w'), ('curtailment', 'total_curtailment_w'), ('loss', 'total_loss_w'), ('served', 'total_served_w'), ('aux_unmet', 'auxiliary_unmet_w')]:
                                energy[policy][metric] += row[field]*dt/3600
                        if abs(outputs['routed_greedy']['total_grid_import_w']-outputs['routed_restricted_optimizer']['total_grid_import_w']) > 1e-7:
                            raise RuntimeError('Greedy/restricted optimizer disagree')
                        log.write(json.dumps({'case': name, 'group': group, 'index': index, 'dt_s': dt, 'parameters': asdict(p), 'input': asdict(s), 'outputs': outputs}, separators=(',', ':'), allow_nan=False)+'\n')
                        steps_count += 1
                        rows_count += len(outputs)
                    b, c = energy['conventional'], energy['routed_restricted_optimizer']
                    valid = b['unmet'] <= 1e-7 and c['unmet'] <= 1e-7 and c['aux_unmet'] <= 1e-7
                    records.append({'case': name, 'group': group, 'steps': len(steps),
                                    'existing_capacity_w': p.conventional_capacity_w, 'link_efficiency': p.link_efficiency,
                                    'standby_w': p.auxiliary_standby_w, 'baseline_grid_wh': b['grid'], 'routed_grid_wh': c['grid'],
                                    'baseline_unmet_wh': b['unmet'], 'routed_unmet_wh': c['unmet'],
                                    'routed_aux_unmet_wh': c['aux_unmet'], 'raw_grid_delta_wh': b['grid']-c['grid'],
                                    'valid_grid_saving_wh': b['grid']-c['grid'] if valid else '',
                                    'comparison_valid': valid, 'controller_grid_delta_wh': energy['routed_greedy']['grid']-c['grid']})
                    if len(records) % 1000 == 0:
                        print(f'{len(records)} cases / {rows_count} dispatches', flush=True)
    with (out/'cases.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    files, tree_hash = source_hashes()
    write_json(out/'manifest.json', {'schema_version': 1, 'seed': SEED, 'days': days, 'random_trials': trials,
                                   'case_count': len(records), 'input_steps': steps_count, 'dispatches': rows_count,
                                   'generated_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version,
                                   'platform': platform.platform(), 'source_tree_sha256': tree_hash,
                                   'source_files_sha256': files, 'evidence': 'synthetic exploratory development; no calibrated population distribution'})
    report = verify(out)
    write_json(out/'audit.json', report)
    summary = {'status': 'pass', 'case_count': len(records), 'input_steps': steps_count, 'dispatches': rows_count,
               'groups': {}, 'independent_audit': report}
    for group in ('seeded_day', 'factorial', 'capped_grid_stress'):
        subset = [r for r in records if r['group'] == group]
        valid = [r for r in subset if r['comparison_valid']]
        savings = [r['valid_grid_saving_wh'] for r in valid]
        summary['groups'][group] = {'cases': len(subset), 'valid_comparisons': len(valid),
                                  'invalid_service_comparisons': len(subset)-len(valid),
                                  'beneficial': sum(x > 1e-7 for x in savings), 'adverse': sum(x < -1e-7 for x in savings),
                                  'equal': sum(abs(x) <= 1e-7 for x in savings),
                                  'min_saving_wh': min(savings) if savings else None, 'max_saving_wh': max(savings) if savings else None}
    write_json(out/'summary.json', summary)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist([r['valid_grid_saving_wh'] for r in records if r['group'] == 'seeded_day'], bins=20, color='#287e89')
    ax.axvline(0, color='#b33c35')
    ax.set(xlabel='Conventional minus added-link grid import (Wh/day)', ylabel='Synthetic days', title=f'{days} seeded synthetic days: savings include standby cost')
    fig.tight_layout()
    fig.savefig(out/'day_savings.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    for eta in [.75, .8, .85, .9, .95, 1]:
        subset = [r for r in records if r['group'] == 'factorial' and r['existing_capacity_w'] == 30 and r['link_efficiency'] == eta]
        ax.plot([r['standby_w'] for r in subset], [r['valid_grid_saving_wh'] for r in subset], marker='o', label=f'link efficiency {eta:.2f}')
    ax.axhline(0, color='black', lw=.8)
    ax.set(xlabel='Dedicated standby load (W)', ylabel='Grid saving in one-hour fixture (Wh)', title='Fixed 30 W existing path / 50 W added path / 100 W PV')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out/'standby_sensitivity.png', dpi=160)
    plt.close(fig)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    write_json(out/'artifact_hashes.json', hashes)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'results/study_20261003')
    parser.add_argument('--days', type=int, default=100)
    parser.add_argument('--trials', type=int, default=10000)
    args = parser.parse_args()
    if args.days < 1 or args.trials < 1:
        parser.error('days and trials must be positive')
    run(args.out.resolve(), args.days, args.trials)
