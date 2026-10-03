"""Analytical, fault, randomized-invariant, mutation, and independent-grid tests."""
from dataclasses import replace
import math
import random
import unittest

from helioroute.model import POLICIES, Parameters, Step, audit, dispatch, optimize_paths
from helioroute.scenarios import load_scenarios


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.p = Parameters(source_efficiency=1, load_efficiency=1,
                            conventional_efficiency=1, conventional_capacity_w=30,
                            link_efficiency=.9, link_capacity_w=50)
        self.s = Step(100, 0, 20, 100)

    def test_golden_exact_baseline_and_hardware_gain(self):
        baseline = dispatch(self.s, self.p, "conventional")
        route = dispatch(self.s, self.p, "routed_restricted_optimizer")
        for field, expected in (("total_renewable_served_w", 50), ("total_grid_import_w", 70),
                                ("total_curtailment_w", 50), ("total_loss_w", 0)):
            self.assertAlmostEqual(baseline[field], expected)
        for field, expected in (("total_renewable_served_w", 95), ("total_grid_import_w", 25),
                                ("total_curtailment_w", 0), ("total_loss_w", 5),
                                ("conventional_send_w", 30), ("link_send_w", 50)):
            self.assertAlmostEqual(route[field], expected)
        self.assertEqual(route["total_served_w"], baseline["total_served_w"])
        self.assertEqual(audit(self.s, self.p, route), [])

    def test_both_directions_are_symmetric(self):
        reverse = dispatch(Step(0, 100, 100, 20), self.p, "routed_restricted_optimizer")
        forward = dispatch(self.s, self.p, "routed_restricted_optimizer")
        self.assertEqual(reverse["direction"], -1)
        self.assertAlmostEqual(reverse["total_grid_import_w"], forward["total_grid_import_w"])

    def test_unconstrained_routing_cannot_create_savings(self):
        p = replace(self.p, conventional_capacity_w=200)
        b = dispatch(self.s, p, "conventional")
        opt = dispatch(self.s, p, "routed_restricted_optimizer")
        forced = dispatch(self.s, p, "routed_link_first")
        self.assertAlmostEqual(b["total_grid_import_w"], 20)
        self.assertEqual(opt["link_send_w"], 0)
        self.assertAlmostEqual(opt["total_grid_import_w"], 20)
        self.assertAlmostEqual(forced["total_grid_import_w"], 25)

    def test_no_sink_means_curtailment(self):
        row = dispatch(Step(100, 0, 20, 0), self.p, "routed_restricted_optimizer")
        self.assertEqual(row["link_send_w"], 0)
        self.assertEqual(row["total_curtailment_w"], 80)

    def test_zero_generation_and_standby_are_not_savings(self):
        s = Step(0, 0, 40, 60)
        p = replace(self.p, auxiliary_standby_w=2)
        row = dispatch(s, p, "routed_restricted_optimizer")
        self.assertEqual(row["total_grid_import_w"], 102)
        self.assertEqual(row["total_served_w"], 100)
        self.assertEqual(row["auxiliary_grid_w"], 2)
        self.assertEqual(audit(s, p, row), [])

    def test_grid_limit_is_explicit_service_failure(self):
        s = Step(0, 0, 0, 100, grid_cap_a_w=0, grid_cap_b_w=50)
        row = dispatch(s, self.p, "routed_restricted_optimizer")
        self.assertEqual(row["total_unmet_w"], 50)
        self.assertEqual(row["service_status"], "policy_service_shortfall")
        self.assertTrue(row["physical_infeasibility_proven"])
        self.assertEqual(audit(s, self.p, row), [])

    def test_unpowered_controller_disables_link(self):
        p = replace(self.p, auxiliary_standby_w=2)
        s = replace(self.s, grid_cap_b_w=1)
        row = dispatch(s, p, "routed_restricted_optimizer")
        self.assertFalse(row["link_enabled"])
        self.assertEqual(row["link_send_w"], 0)
        self.assertEqual(row["auxiliary_unmet_w"], 1)
        self.assertEqual(audit(s, p, row), [])

    def test_stale_and_failed_link_fall_back_to_conventional(self):
        for s in (replace(self.s, telemetry_fresh=False), replace(self.s, link_available=False)):
            for policy in POLICIES:
                row = dispatch(s, self.p, policy)
                self.assertEqual(row["link_send_w"], 0)
                self.assertAlmostEqual(row["total_grid_import_w"], 70)
                self.assertEqual(audit(s, self.p, row), [])

    def test_sending_and_receiving_ratings(self):
        for p in (replace(self.p, link_capacity_w=10), replace(self.p, link_receive_capacity_w=9)):
            row = dispatch(self.s, p, "routed_restricted_optimizer")
            self.assertAlmostEqual(row["link_send_w"], 10)
            self.assertEqual(audit(self.s, p, row), [])

    def test_source_load_and_transfer_losses_independent_arithmetic(self):
        p = replace(self.p, source_efficiency=.8, load_efficiency=.5,
                    conventional_capacity_w=10, conventional_efficiency=.8,
                    link_capacity_w=100, link_efficiency=.5)
        # Raw 100 -> source bus80. Local useful20 consumes40bus. Existing10
        # reaches8; router30 reaches15; B useful=(8+15)*.5=11.5.
        row = dispatch(self.s, p, "routed_restricted_optimizer")
        self.assertAlmostEqual(row["total_renewable_served_w"], 31.5)
        self.assertAlmostEqual(row["total_loss_w"], 68.5)
        self.assertAlmostEqual(row["total_grid_import_w"], 88.5)
        self.assertEqual(audit(self.s, p, row), [])

    def test_parameter_and_profile_validation(self):
        for p in (replace(self.p, link_efficiency=1.1), replace(self.p, source_efficiency=0),
                  replace(self.p, link_capacity_w=-1), replace(self.p, auxiliary_standby_w=-1),
                  replace(self.p, load_efficiency=math.nan)):
            with self.assertRaises(ValueError):
                dispatch(self.s, p, "routed_restricted_optimizer")
        for s in (replace(self.s, pv_a_w=-1), replace(self.s, load_b_w=math.inf),
                  replace(self.s, telemetry_fresh="false")):
            with self.assertRaises(ValueError):
                dispatch(s, self.p, "routed_restricted_optimizer")
        with self.assertRaises(ValueError):
            dispatch(self.s, self.p, "unknown")

    def test_auditor_detects_corruption(self):
        row = dispatch(self.s, self.p, "routed_restricted_optimizer")
        for key in ("served_b_w", "total_grid_import_w", "link_loss_w", "incoming_bus_a_w",
                    "total_renewable_served_w", "total_loss_w", "balance_residual_w"):
            wrong = row.copy()
            wrong[key] += 1
            self.assertTrue(audit(self.s, self.p, wrong), key)
        wrong = row.copy()
        wrong["link_signed_w"] *= -1
        self.assertTrue(audit(self.s, self.p, wrong))
        wrong = dispatch(self.s, self.p, 'conventional')
        wrong['conventional_signed_w'] *= -1
        self.assertTrue(audit(self.s, self.p, wrong))
        wrong = row.copy()
        wrong['pv_available_a_w'] += 1
        wrong['total_available_pv_w'] += 1
        self.assertTrue(audit(self.s, self.p, wrong))

    def test_known_local_first_restriction_is_not_global_infeasibility(self):
        p = replace(self.p, conventional_capacity_w=200, link_capacity_w=200, link_efficiency=1)
        s = Step(100,0,100,100,grid_cap_a_w=100,grid_cap_b_w=0)
        restricted = dispatch(s,p,'routed_restricted_optimizer')
        self.assertEqual(restricted['total_unmet_w'],100)
        self.assertFalse(restricted['physical_infeasibility_proven'])
        # Explicit feasible witness outside the fixed local-first action set:
        # A imports100W grid for its load; A sends all100W PV to B losslessly.
        send, grid_a = 100,100
        self.assertLessEqual(send,p.conventional_capacity_w)
        self.assertLessEqual(grid_a,s.grid_cap_a_w)
        self.assertEqual(grid_a,s.load_a_w)
        self.assertEqual(send*p.conventional_efficiency,s.load_b_w)
        self.assertEqual(s.pv_a_w+grid_a,s.load_a_w+s.load_b_w)

    def test_pairing_rejects_changed_input_and_service(self):
        from helioroute.run import paired, summarize
        base = summarize([dispatch(self.s,self.p,'conventional')],3600)
        candidate = summarize([dispatch(self.s,self.p,'routed_restricted_optimizer')],3600)
        base['input_trace_sha256'] = candidate['input_trace_sha256'] = 'same-test-trace'
        self.assertEqual(paired(base,candidate,'test')['status'],'pass')
        for key in ('total_demand_wh','total_available_pv_wh'):
            original = candidate['energy_wh'][key]
            candidate['energy_wh'][key] += 1
            result = paired(base,candidate,'test')
            self.assertEqual(result['status'],'fail')
            self.assertIsNone(result['valid_grid_saving_wh'])
            candidate['energy_wh'][key] = original
        candidate['input_trace_sha256'] = 'different-trace'
        self.assertEqual(paired(base,candidate,'test')['status'],'fail')

    def test_optimizer_matches_independent_discrete_exhaustion(self):
        # Integer flows on small lossless cases are exact optima; lossy cases use
        # a 0.1W mesh as a lower bound, with <=0.2W quantization gap.
        rng = random.Random(62017)
        for _ in range(45):
            cap = (rng.randint(1, 5), rng.randint(1, 5))
            eta = (rng.choice((.5, .8, 1.)), rng.choice((.5, .9, 1.)))
            surplus, deficit = rng.randint(1, 8), rng.randint(1, 8)
            x, y = optimize_paths(surplus, deficit, cap, eta)
            actual = eta[0]*x+eta[1]*y
            mesh_best = 0.
            for ix in range(cap[0]*10+1):
                for iy in range(cap[1]*10+1):
                    sx, sy = ix/10, iy/10
                    delivered = eta[0]*sx+eta[1]*sy
                    if sx+sy <= surplus+1e-10 and delivered <= deficit+1e-10:
                        mesh_best = max(mesh_best, delivered)
            self.assertGreaterEqual(actual+1e-7, mesh_best)
            self.assertLessEqual(actual-mesh_best, .2+1e-7)

    def test_2000_seeded_property_cases(self):
        rng = random.Random(160289)
        for _ in range(2000):
            p = Parameters(source_efficiency=rng.uniform(.5, 1), load_efficiency=rng.uniform(.5, 1),
                           conventional_efficiency=rng.uniform(.5, 1), conventional_capacity_w=rng.uniform(0, 200),
                           conventional_receive_capacity_w=rng.uniform(0, 200),
                           link_efficiency=rng.uniform(.5, 1), link_capacity_w=rng.uniform(0, 200),
                           link_receive_capacity_w=rng.uniform(0, 200), auxiliary_standby_w=rng.uniform(0, 3))
            s = Step(*(rng.uniform(0, 400) for _ in range(4)),
                     grid_cap_a_w=rng.uniform(0, 400), grid_cap_b_w=rng.uniform(0, 400),
                     link_available=rng.random() > .1, telemetry_fresh=rng.random() > .1)
            rows = {policy: dispatch(s, p, policy) for policy in POLICIES}
            for row in rows.values():
                self.assertEqual(audit(s, p, row), [])
            g, o = rows["routed_greedy"], rows["routed_restricted_optimizer"]
            for key in ("total_renewable_served_w", "total_grid_import_w", "total_unmet_w", "total_loss_w"):
                self.assertAlmostEqual(g[key], o[key], places=6)

    def test_scenarios_are_deterministic_and_every_row_audits(self):
        first = load_scenarios("config/experiments.json")
        second = load_scenarios("config/experiments.json")
        self.assertEqual(first, second)
        for spec, p, steps in first[1]:
            for step in steps:
                for policy in POLICIES:
                    self.assertEqual(audit(step, p, dispatch(step, p, policy)), [], spec['id'])


if __name__ == "__main__":
    unittest.main()
