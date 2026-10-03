# Interpretation of computed results

All figures below come from the fixed development scenarios. They are synthetic, not held-out or measured hardware results. Never sum different scenario energy deltas into a product-saving claim.

| Scenario | Conventional grid Wh | Added-link grid Wh | Valid hardware delta Wh | Unmet useful load Wh (added) |
|---|---:|---:|---:|---:|
| golden_bottleneck | 70.000000 | 25.000000 | 45.000000 | 0.000000 |
| uniform_unconstrained | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| unconstrained_transfer | 20.000000 | 20.000000 | 0.000000 | 0.000000 |
| asymmetric_day | 4047.464672 | 3255.232189 | 792.232483 | 0.000000 |
| reverse_flow | 70.000000 | 25.000000 | 45.000000 | 0.000000 |
| abrupt_changes | 21.504767 | 18.497767 | 3.007000 | 0.000000 |
| zero_generation | 100.000000 | 100.000000 | 0.000000 | 0.000000 |
| standby_negative | 100.000000 | 102.000000 | -2.000000 | 0.000000 |
| receiving_load_removed | 5.706367 | 2.699367 | 3.007000 | 0.000000 |
| rating_clamp | 290.397000 | 280.697000 | 9.700000 | 0.000000 |
| stale_telemetry | 11.412733 | 8.405733 | 3.007000 | 0.000000 |
| link_failure | 8.559550 | 7.056050 | 1.503500 | 0.000000 |
| infeasible_supply_bound | 50.000000 | 50.000000 | invalid: service shortfall | 50.000000 |
| efficiency_order_sensitivity | 36.000000 | 24.000000 | 12.000000 | 0.000000 |
| local_first_counterexample | 0.000000 | 0.000000 | invalid: service shortfall | 100.000000 |

Positive delta means lower grid import after modeled losses/standby and only with fully met common service. Negative delta means more grid import. All valid same-hardware greedy-versus-restricted-solver grid differences are0Wh. Failed service comparisons remain invalid even when raw differences are0.

The synthetic daily mismatch yields792.232483Wh less grid import under its declared artificial profile and hardware assumptions. This single constructed day is not a real-world saving estimate.

The local-first counterexample has100Wh unmet despite a feasible broader policy. The zero-PV supply-bound case has50Wh genuinely unavoidable unmet demand by total energy supply. They are different limitations and both are retained.

Run-specific precise values, hashes and audit residuals are in results/latest/summary.json, manifest.json and artifact_verification.txt. Do not treat a source-tree hash as proof of external certification.
