"""Saved-evidence mutation tests for the independent streamed study auditor."""
import csv
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from helioroute.model import Parameters, Step, POLICIES, dispatch
from verify_study import verify


class StudyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = Parameters(source_efficiency=1, load_efficiency=1, conventional_efficiency=1,
                       conventional_capacity_w=30, link_efficiency=.9, link_capacity_w=50)
        s = Step(100, 0, 20, 100)
        self.item = {'case': 'golden', 'index': 0, 'dt_s': 3600, 'parameters': asdict(p),
                     'input': asdict(s), 'outputs': {policy: dispatch(s, p, policy) for policy in POLICIES}}
        (self.root/'manifest.json').write_text(json.dumps({'case_count': 1, 'dispatches': 5, 'input_steps': 1}))
        self.record = {'case': 'golden', 'steps': 1, 'baseline_grid_wh': 70, 'routed_grid_wh': 25,
                       'baseline_unmet_wh': 0, 'routed_unmet_wh': 0, 'routed_aux_unmet_wh': 0,
                       'raw_grid_delta_wh': 45, 'controller_grid_delta_wh': 0,
                       'comparison_valid': True, 'valid_grid_saving_wh': 45}
        self.save()

    def save(self):
        with gzip.open(self.root/'dispatch.jsonl.gz', 'wt', encoding='utf-8') as stream:
            stream.write(json.dumps(self.item)+'\n')
        with (self.root/'cases.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.record))
            writer.writeheader()
            writer.writerow(self.record)

    def test_valid_saved_golden(self):
        self.assertEqual(verify(self.root)['checked_dispatches'], 5)

    def test_modified_path_loss_is_rejected(self):
        self.item['outputs']['routed_greedy']['link_loss_w'] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, 'path loss'):
            verify(self.root)

    def test_fabricated_summary_saving_is_rejected(self):
        self.record['valid_grid_saving_wh'] = 46
        self.save()
        with self.assertRaisesRegex(ValueError, 'saving differs'):
            verify(self.root)

    def test_missing_policy_is_rejected(self):
        del self.item['outputs']['routed_greedy']
        self.save()
        with self.assertRaisesRegex(ValueError, 'missing or extra policy'):
            verify(self.root)
