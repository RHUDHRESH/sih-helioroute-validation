# Claim-to-evidence ledger

All present results are **synthetic dispatch simulation**. No result is hardware-measured or field-validated. Source context is recovered submission text for HELIOROUTE, SIH26217, Prototype Pioneers Team160289; attached current PDF diagrams could not be visually inspected. This implementation declares a test topology and does not claim to reproduce uninspected diagrams.

| Claim | Status and evidence | Boundary / remaining work |
|---|---|---|
| Source, service, curtailment and loss accounting closes | Tested in analytical, randomized and per-step CSV audits; `test_report.txt`, `artifact_verification.txt` | Numerical correctness within a scalar model; not instrument calibration |
| An added parallel route can reduce grid import under coincident surplus/deficit and a constrained existing path | Demonstrated only in specified synthetic scenarios, including golden100+25=120+5Wh | Requires actual electrically feasible endpoints, conversion efficiency, ratings and useful receiving demand |
| Useful service is equal for a valid saving comparison | Required by paired gate and shared trace hash; failed-service comparisons emit no valid saving | Fixed useful electrical load only; no pump water/head/tank validation |
| A sophisticated optimizer outperforms greedy | **Not supported**: loss-aware greedy and the restricted surplus-sharing solver agree | No storage, forecasts, scheduling or time coupling; simple control is sufficient for this restricted model |
| Restricted solver is globally service optimal | **False in general**: `local_first_counterexample` retains a100Wh policy shortfall and an explicit feasible alternative outside its action set | Need broader service-allocation controller before capped-backup optimization claims |
| Routing always saves energy | **False**: unconstrained path gives a tie; forced lossy routing and auxiliary standby make results worse | Include measured loss/standby curves and a break-even study |
| Stale telemetry / link failure produces a zero route setpoint | Tested as instantaneous step-boundary flags, with conventional fallback | No electrical response, trip latency, fault energy or actual protections tested |
| Specified real-power path caps are respected | Sending/receiving W caps audited in every step | Not AC current, VA, voltage, thermal or conductor compliance |
| Reversible sharing is represented | Reverse-flow fixture and randomized signed-direction checks | Not verified bidirectional converter hardware |
| Storage or delayed flexible-work improvement | **Not run / absent** | Need fair initial/final energy/tank states and useful-service deadlines before adding |
| 24V RMS /48V DC /300W design is valid | **Not tested** |24V RMS peaks33.9V; regulated48V bus needs active boost. Validate actual topology, active stages, MPPT, thermal ratings and safety separately |
| Mains/grid compliance, electrical stability, protection, MPPT, EMC or prototype readiness | **Not tested** | Qualified design review and instrumented isolated hardware test program required |
| Real-world/generalized percentage saving | **Not supported** | No real weather/load traces, held-out test set, calibrated loss curves or field trials |

## Judge-safe statement

“Under this explicitly defined synthetic two-feeder model, adding a parallel path recovers some otherwise-curtailed PV when usable demand exists across a delivery bottleneck. We account for every source, load and modeled loss, and show cases with no benefit or worse performance. The simple loss-aware greedy controller matches a solver restricted to the same local-first surplus-sharing action set. Hardware, electrical dynamics and real-world savings remain unvalidated.”
