# Artifact schema v1

`schema_version: 1` appears in experiment configuration, summary, manifest, replay and every input/dispatch CSV row. Consumers must reject an unsupported version rather than guess changed units/semantics.

## Configuration

`config/experiments.json` contains evidence_label, evaluation_split, deterministic seed, default_parameters and an ordered scenarios array. Each scenario has unique id, description, positive dt_s, optional parameter overrides, and either an explicit steps array or the named deterministic asymmetric_day generator with count. A step has nonnegative finite pv_a_w/pv_b_w/load_a_w/load_b_w, optional grid_cap_a_w/grid_cap_b_w (default1e9W), link_available and telemetry_fresh booleans (defaulttrue).

Efficiencies are finite in(0,1]. Capacities and standby power are finite and nonnegative. Ratings are sending/receiving interval-average W. No implicit storage or export exists.

## inputs.csv

One common record per scenario/step. Unique key: `(scenario, step_index)`. Required columns: schema_version, scenario, step_index, time_s, dt_s and all Step fields above. time_s=step_index×dt_s. Inputs are shared by every policy; there are no policy-specific demand/weather traces.

## dispatch.csv

Unique key: `(scenario, policy, step_index)`. Every input key occurs once for each declared policy. time_s/dt_s match inputs. `_w` suffix always means interval-average real power. Direction is -1 for B→A,0 for no transfer,+1 for A→B. Sending powers are nonnegative; signed powers equal direction×sending power.

Per feeder: pv_available, demand, pv_used_raw, source_loss, local_bus, incoming_bus, outgoing_bus, load_bus, load_loss, renewable_served, grid_import, served, unmet and curtailment, suffixed `_a_w` / `_b_w`.

Paths: conventional_send_w, link_send_w, signed versions, and conventional_loss_w/link_loss_w. link_enabled is a boolean. Totals and auxiliary fields explicitly distinguish useful grid import from total grid import including controller standby. `balance_residual_w` is an independently checkable signed residual.

`service_status` is `met` or `policy_service_shortfall`. `physical_infeasibility_proven` is separate: true only if the optimistic total available PV plus grid capacities cannot cover demand+requested auxiliary. `supply_lower_bound_shortfall_w` gives this conservative bound. False does not prove feasibility; it means this limited certificate did not establish impossibility.

## summary.json

Contains schema_version, evidence_label, evaluation_split, optimizer_scope, test summary, scenario count, dispatch-row count and scenario_results. Each scenario retains declared parameters and five variants. Energy fields end `_wh`; integrations use dt_s/3600. Each ratio has numerator, denominator, unit, estimate, status, reason and confidence_interval. Zero denominators produce null estimate and not-applicable status. No statistical CI is claimed.

`useful_service_status`/`system_service_status` are pass/fail. A pass means the configured loads were met, not that hardware or safety is accepted. `policy_shortfall_step_count` and `physical_infeasibility_proven_step_count` preserve the distinction.

Comparison A changes topology; comparison B changes the controller on identical topology. Fields include same_required_demand, same_available_pv, same_input_trace, raw_grid_difference_wh, valid_grid_saving_wh and reason. Valid saving is null on any failed fairness or service gate. A negative valid saving is an energy cost, not an error to discard.

## manifest.json / replay.json / hashes

Manifest binds source files/tree, configuration, recorded input trace, dependency lock, deterministic seeds, Python/OS/runtime, units, tolerances and explicit evidence scope. The runner does not itself perform browser visual QA and records that as not-run. Separate local browser smoke evidence is documented in BROWSER_QA.md.

Replay contains the same scenario results, input rows and dispatch rows used by the CSV audit. Its data is checked against exported CSV and summary before use. The viewer never creates alternative performance values. artifact_hashes.json hashes final output files; it does not recursively hash itself.

## Numeric tolerance

Per-step absolute audit tolerance:1e-7W. Whole-run absolute tolerance:1e-7Wh. Restricted solver comparison tolerance:1e-8W. These are floating-point test thresholds for small synthetic powers; they are not measured physical uncertainty or suitable scaling guarantees for arbitrary large systems.
