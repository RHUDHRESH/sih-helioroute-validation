# HELIOROUTE: bounded synthetic validation

Prototype Pioneers · Team160289 · SIH26217

## Expanded study — 3 October 2026

The expanded study executes **195,080 dispatches** across 100 synthetic days, 216 factorial settings and 10,000 capped-grid stress cases. Accounting and saved-evidence audits pass. The added link improves 21 of the 100 varied daily fixtures and increases grid use in 72; standby cost matters. Greedy and restricted optimizer agree throughout.

Read the [study report](STUDY_REPORT.md), [browser verification](BROWSER_QA.md) and [publication guide](GITHUB_READY.md). Results, raw compressed dispatches, hashes and figures are in `results/study_20261003/`.

Windows: `python -m venv .venv`, then `.\.venv\Scripts\python.exe -m pip install -r requirements.lock`. Run `.\run.ps1 -Python .\.venv\Scripts\python.exe` for the baseline. Run `.\.venv\Scripts\python.exe study.py --out results/my-study` for the expanded study. A fresh output directory preserves previous evidence.

This is a reproducible **synthetic discrete-time energy-flow model**, not an electrical transient simulation, field experiment, or working converter. It tests accounting and a declared routing mechanism. Every efficiency, rating and PV/load trace is an explicit synthetic assumption. It is not evidence of a 24 V / 48 V / 300 W hardware implementation.

## Run it

Python 3.10+ is needed. The model, tests, CSV/JSON export, independent verifier and local viewer use only the standard library. Full plots use the pinned dependencies in `requirements.lock`.

```sh
# With plotting dependencies available (the delivered environment has them):
./run.sh

# Offline / fresh standard-library Python, without plots:
./run.sh --no-plots

# Optional clean plotting environment:
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
./run.sh

# Open the side-by-side replay in a browser:
./serve.sh
# http://127.0.0.1:8766/viewer/
```

`run.sh` runs the tests first, executes every fixed scenario and policy, exports real computed results, independently re-audits the exported CSV, and produces four PNG plots. Failure is visible and exits nonzero. `--no-plots` explicitly marks plots not-run; it does not claim full visual regeneration. The delivered `results/latest/` includes the full generated output. Reruns replace files in the selected output directory; use `--output results/my-run` to preserve a separate run. The viewer always uses `results/latest/`.

Additional commands:

```sh
python3 -m unittest discover -s tests -v
python3 verify_artifacts.py results/latest
python3 -m helioroute.run --output results/reproduction --no-plots
```

The viewer is a **replay of computed synthetic results**, not a live electrical simulator. Choose a scenario, compare hardware or controllers, and move the shared timeline. Play, Pause, Next and First change only the replay position. The lower panel reports whole-run Wh; the paired cards show the selected step's average W. It works locally without a remote service. Bind is localhost only.

## Exact modeled topology and boundary

- Each feeder A/B has available raw electrical PV, an identical source conversion stage, a feeder bus, an identical useful-load conversion stage, and a fixed useful electrical load
- An existing bidirectional path connects the two feeder buses. It has separate sending/receiving average-real-power caps and constant efficiency
- The optional routing link connects those **same two bus endpoints in parallel**, so it can bypass the existing path's capacity constraint. This is additional hardware
- Grid backup is ideal and supplied at each useful-load endpoint, within its declared per-step cap. Grid energy cannot be routed; PV cannot be exported
- Optional controller standby is a **dedicated grid-fed load at B**, counted against B's grid cap before useful-load backup. It remains a cost when transfer is zero. An underpowered controller disables the added link
- Unused available PV is curtailed **before** its source converter. Source conversion losses apply only to actually drawn PV. Incoming path energy passes through the receiving useful-load converter once
- No storage, tank, flexible load, reactive power, current, voltage, switching, dynamics, thermal state, transient DC-link energy, export or time-coupled decisions exist

Raw PV is upstream of the modeled common conversion stage, not claimed to be a calibrated PV-array or AC-inverter boundary. The hand-arithmetic fixtures set common conversion efficiencies to 1. PV DC-to-AC architecture and actual proposed slide diagrams remain unresolved. Both alternatives use identical boundaries.

## Two comparisons; no invented optimizer advantage

**A: conventional topology vs added link.** Same inputs, fixed useful demand, existing path, grid access and conversion assumptions. The optional link and its loss/standby are the hardware intervention. A positive difference does not validate a new optimization algorithm.

**B: loss-aware greedy vs restricted surplus-sharing optimizer.** Identical optional-link hardware, observations and feasible action set. Both first allocate PV locally. The greedy rule uses the more efficient available path first. The solver independently enumerates all vertices of the remaining two-variable path LP. It is exact **conditional on this local-first/PV-surplus-only restriction**. Neither sees future data.

They agree in this model. There is no optimizer-superiority finding. `routed_existing_first` and `routed_link_first` are explicitly fixed-order negative-control ablations, not strong primary baselines.

### Known limitation: capped grid can require a different allocation

`local_first_counterexample` has PV A=100 W, loads A=B=100 W, grid caps A=100 W and B=0 W, and a lossless uncongested path. Local-first consumes all PV at A and leaves B's 100 W unmet. A broader controller could send all 100 W PV to B and use 100 W grid at A, serving both loads. A regression test includes that feasible witness.

Therefore the output says **policy service shortfall**, not physical infeasibility. The separate `physical_infeasibility_proven` flag is used only when even an optimistic total source-plus-grid energy bound is insufficient. The restricted solver is not a general distribution-network service-allocation optimizer.

## Evidence produced

- 15 declared development scenarios, including positive, equal-result and adverse cases
- 21 tests, with 2,000 fixed-seed randomized profiles across five policies, 45 small independent mesh-enumeration cross-checks and four streamed-study evidence mutation checks
- `inputs.csv`: the one common input trace per scenario
- `dispatch.csv`: every node/source/sink/loss, routing direction, status and residual for every policy/step
- `summary.json`: Wh integrals, metric numerators/denominators, full/failed-service statuses and paired deltas; invalid saving claims become `null`
- `manifest.json`: exact source/config/input/lock hashes, seeds, runtime, model scope, units and tolerances
- `artifact_verification.txt`: an independent CSV audit that imports no dispatch implementation
- `replay.json`: generated trace data for the side-by-side viewer
- `plots/`: four figures derived from the generated CSV/JSON, not illustrations of hypothetical results
- `test_report.txt`, `test_summary.json`, `artifact_hashes.json`

A deterministic zero-generation run gives PV ratios `null` with reason “Zero denominator”. No statistical confidence interval is manufactured for these fixed synthetic fixtures. All cases are **exploratory development fixtures**, not a locked held-out evaluation set.

See [the claim ledger](CLAIM_LEDGER.md), [model equations and assumptions](MODEL.md), and [result interpretation](RESULTS.md).

## Headline hand-check

In `golden_bottleneck`, one hour of PV100 Wh supplies useful demand120 Wh. Local A uses20 Wh, the existing path carries30 Wh, and the added path may send50 Wh at90% efficiency.

| Quantity | Conventional | Added link |
|---|---:|---:|
| Same useful electrical service | 120 Wh | 120 Wh |
| Grid import | 70 Wh | 25 Wh |
| Curtailed PV | 50 Wh | 0 Wh |
| Conversion/path losses | 0 Wh | 5 Wh |

Added-link closure: 100 PV + 25 grid = 120 useful service + 5 loss. This manufactured scenario deliberately provides otherwise-curtailed supply, receiving demand, and additional path capacity; the benefit is conditional on those assumptions.

The unconstrained-existing-path fixture has **no optimized hardware benefit**. Forcing energy through the less efficient link increases grid import. With no PV and a 2 W standby draw, added hardware imports 102 Wh for the same 100 Wh useful load versus 100 Wh conventionally.

## Reproducibility and safety boundary

Core arithmetic does not use an external optimization package. Default profile seed 26217, randomized property seed 160289, mesh seed 62017. Per-step audit tolerance is 1e-7 W and cumulative tolerance 1e-7 Wh; these are numerical thresholds, not measurement accuracy. Source tree hash, recorded inputs, dispatch CSV and summary are stable for unchanged source/configuration; manifest timestamp and platform metadata vary.

Ratings here are synthetic **average real power**, not proven electrical current/apparent-power limits. Nothing energizes hardware. The proposed 24 V RMS source peaks at approximately 33.9 V; a regulated 48 V bus would require active boost conversion, and bidirectional hardware/control remain untested. No MPPT, DC-link regulation, protection, mains compliance, converter stability or prototype rating is established.

## Verification status

The delivered build also passes 12 DOM-free JavaScript replay-control tests using Node 24.19.0. Local Microsoft Edge browser smoke checks cover initial values, scenario changes, timeline stepping and controller comparison; screenshots are in docs/BROWSER_QA.md. Full accessibility and cross-browser review remain unmeasured. Baseline and study PNG plots were inspected. See docs/TEST_MATRIX.md for requirement mapping and docs/SCHEMA.md for versioned input/output contracts.
