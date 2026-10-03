# HELIOROUTE

### Measure the value of renewable-energy routing before building the hardware.

**Smart India Hackathon · SIH26217 · Prototype Pioneers · Team 160289**

HELIOROUTE is a reproducible research codebase for a two-feeder renewable-energy system. It investigates whether an additional routing path can turn otherwise-curtailed PV into useful electrical service—and whether conversion losses and controller standby erase that benefit.

The repository includes a declared synthetic energy-flow model, five dispatch policies, broad parameter studies, independent evidence audits and requirement-to-test traceability. Every reported number can be traced to a saved input and dispatch record.

> **Research question:** When does additional transfer capacity reduce grid energy while delivering the same useful service?

## Evidence at a glance

| Validation layer | Executed evidence |
|---|---:|
| Expanded dispatch study | **195,080 dispatch records** |
| Daily profiles | **100 synthetic days**, 5-minute resolution |
| Factorial sensitivity | **216 capacity / efficiency / standby settings** |
| Capped-grid stress | **10,000 seeded cases** |
| Python verification | **21 tests passed**, including artifact-mutation checks |
| Existing randomized regression | **2,000 profiles × five policies** |
| Independent optimizer cross-check | **45 mesh-enumeration cases** |
| Baseline replay | **15 scenarios / 845 dispatch rows** |
| Independent study accounting | Maximum residual **6.8213 × 10⁻¹³ W** |

**Hosted validation:** the [initial release passed GitHub Actions](https://github.com/RHUDHRESH/sih-helioroute-validation/actions/runs/37095304743), including baseline validation and independently audited study smoke checks.

These are executed software simulations with explicit synthetic assumptions. Voltage, current, converter dynamics and physical hardware performance are outside the present evidence boundary.

## The finding that matters

The added link helps when useful receiving demand, otherwise-curtailed PV and a transfer bottleneck coexist. It also consumes energy. The expanded daily study includes both outcomes:

| Outcome across 100 varied synthetic days | Days |
|---|---:|
| Reduced grid import | **21** |
| Equal result | **7** |
| Increased grid import | **72** |

Daily grid saving ranges from **−240.00 to +424.14 Wh/day**. Standby demand often exceeds the energy recovered by routing. These fixture counts describe the declared exploratory distribution; they are not probabilities of field success.

![Daily grid-energy sensitivity](results/study_20261003/day_savings.png)

The result identifies a concrete design priority: **minimize controller standby and establish the actual source/demand mismatch before adding routing hardware.**

## A result you can check by hand

In the one-hour `golden_bottleneck` fixture, PV availability is 100 Wh and useful demand is 120 Wh. The existing path can send 30 W. The additional path can send 50 W at 90% efficiency.

| Energy ledger | Conventional topology | Added routing link |
|---|---:|---:|
| Useful electrical service | 120 Wh | 120 Wh |
| Grid import | 70 Wh | 25 Wh |
| Curtailed PV | 50 Wh | 0 Wh |
| Conversion/path loss | 0 Wh | 5 Wh |

**Closure: 100 Wh PV + 25 Wh grid = 120 Wh useful service + 5 Wh loss.**

The 45 Wh reduction comes from additional usable path capacity under the declared conditions. When the existing path already carries all useful surplus, the added link provides no routing benefit and its standby remains a cost.

## Hardware benefit and controller benefit are separate experiments

**Comparison A:** conventional topology versus an added parallel routing path. Inputs, useful demand, common conversion stages and grid access are matched. Additional capacity, link loss and standby are the hardware intervention.

**Comparison B:** loss-aware greedy routing versus an exact restricted surplus-sharing optimizer on identical hardware. The optimizer enumerates the vertices of a two-variable linear program after fixed local-first allocation. Both controllers agree throughout the expanded study. The evidence supports **no optimizer-superiority claim**.

The known `local_first_counterexample` is retained: with binding grid caps, a broader service-allocation policy can serve loads that this restricted controller misses. Consequently, policy service shortfall is distinguished from physically proven supply insufficiency. Savings are withheld when useful-service or controller-supply requirements fail.

## Reproduce the evidence

Python 3.12 is used for the delivered run. Core simulation, tests and auditors use the standard library; PNG generation uses the pinned plotting dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock

# Tests, baseline dispatch, CSV audit and figures
.\.venv\Scripts\python.exe -m helioroute.run

# Full study; choose a fresh output directory
.\.venv\Scripts\python.exe study.py --out results/my-study
.\.venv\Scripts\python.exe verify_study.py results/my-study
```

Standard-library baseline: `python -m helioroute.run --no-plots`. Reduced study: `python study.py --days 2 --trials 50 --out results/my-smoke`. Windows wrapper: `run.ps1`. Linux/macOS users can run the same Python entrypoints.

The original baseline can be explored locally with `python -m http.server 8766 --bind 127.0.0.1`, then open `http://127.0.0.1:8766/viewer/`. It replays saved computation. App screenshots are excluded from publication.

## Research package

| Artifact | What it establishes |
|---|---|
| [Expanded study report](docs/STUDY_REPORT.md) | Sampling design, complete outcome counts, sensitivity and interpretation |
| [Model and equations](docs/MODEL.md) | Topology, conversion boundaries, feasibility assumptions and accounting |
| [Claim ledger](docs/CLAIM_LEDGER.md) | Supported statements and measurements still required |
| [Requirement-to-test matrix](docs/TEST_MATRIX.md) | Traceability from requirements to executable evidence |
| [Output schema](docs/SCHEMA.md) | Units, statuses, pairing rules and provenance contracts |
| [Study summary](results/study_20261003/summary.json) | Machine-readable study outcomes |
| [Case-level results](results/study_20261003/cases.csv) | Every beneficial, equal, adverse and invalid comparison |
| [Raw dispatch evidence](results/study_20261003/dispatch.jsonl.gz) | Inputs, parameters and all five outputs at every step |
| [Independent audit](results/study_20261003/audit.json) | Recomputed conservation, limits and saved-result consistency |

`helioroute/model.py` contains the model and dispatch policies. `study.py` defines the expanded experiment. `verify_study.py` independently reads serialized records without importing the dispatch implementation. `tests/test_study_audit.py` checks that altered losses, fabricated savings and missing policies are rejected. Git attributes preserve result bytes so evidence hashes survive checkout.

## Next engineering milestone

1. Freeze the converter topology and controller supply architecture.
2. Measure standby and conversion efficiency across operating points.
3. Integrate a service-allocation controller that handles binding grid caps.
4. Validate protection, voltage/current limits, thermal behavior and switching/control stability on a calibrated prototype.
5. Evaluate measured site traces before claiming deployment energy benefit or payback.

**The deliverable is a verifiable decision basis for the next prototype: reproducible inputs, conserved energy, fair baselines and explicit adverse cases.**
