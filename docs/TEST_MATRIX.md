# Requirement-to-test traceability, v1

This is a bounded engineering verification package, not an assertion of ISO/IEC certification, product readiness, electrical safety compliance, or industry-wide acceptance. Failed, blocked, and untested stages remain explicit.

| ID | Requirement | Executable evidence / artifact | Outcome meaning |
|---|---|---|---|
| H-01 | Golden source/service/loss arithmetic | `test_golden_exact_baseline_and_hardware_gain`; golden CSV rows |70→25Wh grid with same120Wh useful load,5Wh loss |
| H-02 | No negative power, phantom source or opposing flow | `test_2000_seeded_property_cases`; all-row `audit`; independent CSV verifier |2,000 deterministic random profiles ×5 policies; node and global residuals bounded |
| H-03 | Separate source/load/path losses and curtailment | `test_source_load_and_transfer_losses_independent_arithmetic`; golden ledger PNG | Each conversion counted once at a declared boundary |
| H-04 | Respect sending/receiving ratings and grid limits | `test_sending_and_receiving_ratings`; `test_grid_limit_is_explicit_service_failure`; rating_clamp | Real-power caps only, not electrical current/VA limits |
| H-05 | Fair input/useful service comparison | `test_pairing_rejects_changed_input_and_service`; immutable input hash; independent pairing audit | Any trace/PV/demand mismatch or unmet service invalidates savings claim |
| H-06 | No unjustified solver superiority | `test_optimizer_matches_independent_discrete_exhaustion`; 2,000 greedy/solver equality cases | Restricted solver matches mesh bound; loss-aware greedy agrees |
| H-07 | Preserve known controller limitation | `test_known_local_first_restriction_is_not_global_infeasibility`; local_first_counterexample | Feasible broader-policy witness retained; policy shortfall is not physical impossibility |
| H-08 | Routing cannot always help | `test_unconstrained_routing_cannot_create_savings`; uniform/unconstrained and standby_negative | Ties and losses retained; fixed-order ablations labelled |
| H-09 | No invented destination/storage sink | `test_no_sink_means_curtailment`; receiving_load_removed | No storage/export means unused source is curtailed |
| H-10 | Fault flags disable routing | `test_stale_and_failed_link_fall_back_to_conventional`; `test_unpowered_controller_disables_link` | Instantaneous step-boundary fallback only; no actual trip latency |
| H-11 | Both modeled flow directions and abrupt changes | `test_both_directions_are_symmetric`; reverse_flow and abrupt_changes | Scalar accounting in both directions, not bidirectional hardware proof |
| H-12 | Reject corrupt inputs/outputs | `test_parameter_and_profile_validation`; `test_auditor_detects_corruption`; manifest and fixed-config binding | Nonfinite/negative values, changed inputs, signs/totals, modified artifacts rejected |
| H-13 | Reproduce same trace | `test_scenarios_are_deterministic_and_every_row_audits`; two-run file-hash comparison | Same inputs, CSV and summary under unchanged source/configuration |
| H-14 | Correct output-driven replay controls | `node tests/test_viewer.js results/latest`; viewer_logic_tests.json |12 DOM-free JavaScript tests, including compare, timeline, play/pause/first/end and visible failure |
| H-15 | Visual browser rendering | Local Microsoft Edge smoke review on 3 October 2026; docs/BROWSER_QA.md | Initial values, scenario changes, next-step and comparison controls checked; full accessibility unmeasured |
| H-16 | Real electrical system performance | Not run | Requires architecture/schematic, calibrated hardware and a separate safety-reviewed program |

## Acceptance gates

1. Python test suite passes; independent CSV audit passes; source/config/input provenance is retained
2. No primary saving number is emitted for unmatched inputs or policy service shortfall
3. Greedy/solver equality and all negative cases remain visible
4. DOM-free logic tests and real-browser smoke evidence remain distinct
5. No hardware or standards-certification claim is inferred from software tests

The checked-in CI workflow provides standard-library baseline validation and an expanded-study smoke job. The [initial release passed hosted GitHub Actions on 3 October 2026](https://github.com/RHUDHRESH/sih-helioroute-validation/actions/runs/37095304743). Local verification and hosted verification remain separately recorded.
