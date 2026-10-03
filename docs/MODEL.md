# Model specification and accounting

## Units and state

All step variables are interval-average W. Integrated energy is W × dt_s / 3600 = Wh. Time steps are synthetic, not a solver discretization of an electrical plant. No state is carried between intervals and no storage endpoint can hide a gain.

For each feeder i, available raw PV is G_i, useful demand is L_i, source efficiency is es and load efficiency is eu. These efficiencies are identical across feeders.

Fixed local-first allocation:

- usable available source bus: es × G_i
- local bus use: min(es × G_i, L_i / eu)
- donor bus surplus S: available source bus minus local bus use
- receiver bus deficit D: L_i / eu minus local bus use

Only one direction can have donor surplus and receiving deficit. The existing path sends x and the added path sends y. Both are nonnegative in the same direction. With path efficiencies ee/el and sending/receiving ratings, their effective sending caps are min(C_send, C_receive / eta).

The restricted optimizer maximizes ee × x + el × y, subject to x + y ≤ S, ee × x + el × y ≤ D and both path caps. It enumerates pairwise intersections of the six boundary lines. Among equal delivery it minimizes sent power, then added-link power. Loss-aware greedy fills the higher-efficiency path first; ties prefer the existing path. They solve the same continuous fractional allocation problem.

This is exact only after local-first allocation. Binding grid caps can require substituting grid for local PV and sending that PV elsewhere, an action excluded by this model's controllers. The counterexample is preserved in code, tests, outputs and the viewer.

## Node accounting

For the donor: raw source used = (local bus use + outgoing path power) / es. For the receiver: raw source used = local bus use / es. Incoming power is ee × x + el × y. Useful PV-derived service is eu × (local bus use + incoming power).

- source conversion loss = raw source used × (1 − es)
- useful-load conversion loss = total load bus power × (1 − eu)
- path loss = sent path power × (1 − path efficiency)
- curtailment = available raw PV − raw source used
- useful grid import = min(remaining useful demand, remaining grid cap)
- useful service = PV-derived useful service + useful grid import
- unmet useful demand = required useful demand − useful service

The router's optional standby supply is ideal grid power at B, explicitly deducted from B's grid capacity. Actual standby consumed is capped by available grid supply; any standby shortfall disables the added link and creates a system-service shortfall flag. This is a declared synthetic auxiliary arrangement, not a measured control-power architecture.

## Whole system

At every step and after integration:

available raw PV + total grid import = useful service + curtailed raw PV + source/load/path losses + actual standby consumption

Demand = useful service + unmet useful demand. Unmet demand is not counted as a delivered sink. PV capture = raw PV used / raw available PV; PV-to-useful fraction = PV-derived useful service / raw available PV. They differ whenever losses occur. Zero denominators are null.

The in-process audit binds reported source/demand values to immutable inputs, checks nodes and totals, both-end path/grid ratings, signs, no opposite transfers and global balance. `verify_artifacts.py` separately reconstructs these calculations from exported primitive CSV columns. Mutation tests intentionally corrupt reported values and input totals.

## Fault assumptions

`telemetry_fresh=False` or `link_available=False` immediately imposes added-link capacity0. Conventional path/local dispatch still use current true local values. This assumes a trusted independent local fallback and instantaneous removal at a simulation boundary. It does not test sensing/communication delay, command expiry/reordering, control-loop latency, a DC-link transient, thermal protection or safe restart. These remain separate hardware/protocol work.

## Explicit assumptions that favor a apparent routing benefit

1. Added parallel hardware can bypass the declared bottleneck and has spare receiving capacity
2. Surplus PV and receiving demand coincide in time; the main synthetic day deliberately creates that mismatch
3. Demand is fixed useful electrical service with no hydraulic/service-quality conversion
4. Default standby is zero because no measurement exists; a separate2 W adverse case exposes that omission
5. Efficiencies are constant synthetic values, independent of load, voltage, direction and temperature
6. True current local source/load values are available with no sensing error, transport delay or switching costs
7. Load-side backup is independent and ideal within caps; no AC power-flow/coupled utility constraint is modeled

None of these are established by the recovered submission or a physical prototype. A real architecture could invalidate the modeled benefit.
