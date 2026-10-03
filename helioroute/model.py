"""Two-feeder dispatch with an existing bottleneck and an optional parallel link.

All instantaneous quantities are average watts over one discrete step. The model
has no storage, transient dynamics, reactive power, voltage, or electrical current.
Both feeders have the same source and load conversion efficiencies. Local-first
is a imposed controller restriction. With unconstrained load-side grid backup it
maximizes PV-derived useful service, but binding grid caps can make it miss useful
service that a broader network controller could supply. The exact optimization is
conditional on the local-first/PV-surplus-only action set. It is not a global
service-allocation solver. The remaining optimization has two nonnegative path-
flow variables and at most one direction. No energy can circulate, flow both ways,
or be stored between steps.
"""

from dataclasses import asdict, dataclass
from itertools import combinations
import math


TOL = 1e-8
POLICIES = ("conventional", "routed_greedy", "routed_restricted_optimizer", "routed_existing_first", "routed_link_first")


@dataclass(frozen=True)
class Parameters:
    source_efficiency: float = 0.98
    load_efficiency: float = 0.97
    conventional_efficiency: float = 0.99
    conventional_capacity_w: float = 30.0  # Sending-bus average power rating
    conventional_receive_capacity_w: float = 1e9
    link_efficiency: float = 0.93
    link_capacity_w: float = 100.0  # Sending-bus average power rating
    link_receive_capacity_w: float = 1e9
    auxiliary_standby_w: float = 0.0  # Dedicated grid-fed controller at B, explicit sensitivity

    def validate(self):
        for key, value in asdict(self).items():
            if not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
            if key.endswith("efficiency") and not 0 < value <= 1:
                raise ValueError(f"{key} must be in (0, 1]")
            if key.endswith("_w") and value < 0:
                raise ValueError(f"{key} must be nonnegative")


@dataclass(frozen=True)
class Step:
    pv_a_w: float
    pv_b_w: float
    load_a_w: float
    load_b_w: float
    grid_cap_a_w: float = 1e9  # Grid is an ideal load-side backup within this cap
    grid_cap_b_w: float = 1e9
    link_available: bool = True
    telemetry_fresh: bool = True

    def validate(self):
        for key, value in asdict(self).items():
            if key in ("link_available", "telemetry_fresh"):
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be bool")
            elif not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")


def _ordered_paths(surplus, deficit, capacities, efficiencies, order):
    """Feasible causal greedy rule; no future profile information is used."""
    flow = [0.0, 0.0]
    for path in order:
        send = min(capacities[path], surplus, deficit / efficiencies[path])
        send = max(0.0, send)
        flow[path] = send
        surplus = max(0.0, surplus - send)
        deficit = max(0.0, deficit - efficiencies[path] * send)
    return tuple(flow)


def optimize_paths(surplus, deficit, capacities, efficiencies):
    """Restricted surplus-sharing LP, exact conditional on local-first allocation.

    Maximize eta_existing*x + eta_link*y, subject to:
      0<=x<=C_existing, 0<=y<=C_link, x+y<=surplus,
      eta_existing*x+eta_link*y<=deficit.
    Among equal delivered power, minimize sent power, then added-link use.
    This tie break avoids burning extra energy merely to reduce curtailment.
    The tiny feasibility tolerance is numerical, not an extra power allowance.
    """
    ce, cl = capacities
    ee, el = efficiencies
    lines = [(1., 0., 0.), (0., 1., 0.), (1., 0., ce), (0., 1., cl),
             (1., 1., surplus), (ee, el, deficit)]
    candidates = [(0., 0.)]
    for (a, b, c), (d, e, f) in combinations(lines, 2):
        determinant = a * e - b * d
        if abs(determinant) < 1e-14:
            continue
        x = (c * e - b * f) / determinant
        y = (a * f - c * d) / determinant
        if (x >= -TOL and y >= -TOL and x <= ce + TOL and y <= cl + TOL
                and x + y <= surplus + TOL and ee*x + el*y <= deficit + TOL):
            candidates.append((min(ce, max(0., x)), min(cl, max(0., y))))
    best = (0., 0.)
    for flow in candidates:
        delivered = ee * flow[0] + el * flow[1]
        best_delivered = ee * best[0] + el * best[1]
        if delivered > best_delivered + TOL:
            best = flow
        elif abs(delivered - best_delivered) <= TOL:
            if sum(flow) < sum(best) - TOL:
                best = flow
            elif abs(sum(flow) - sum(best)) <= TOL and flow[1] < best[1] - TOL:
                best = flow
    return best


def dispatch(step: Step, params: Parameters, policy: str) -> dict:
    step.validate()
    params.validate()
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    gs = [step.pv_a_w, step.pv_b_w]
    loads = [step.load_a_w, step.load_b_w]
    caps = [step.grid_cap_a_w, step.grid_cap_b_w]
    auxiliary_requested = params.auxiliary_standby_w if policy != "conventional" else 0.
    auxiliary_grid = min(auxiliary_requested, caps[1])
    auxiliary_unmet = auxiliary_requested - auxiliary_grid
    caps[1] -= auxiliary_grid
    es, eu = params.source_efficiency, params.load_efficiency
    available_bus = [g * es for g in gs]
    local_bus = [min(g, load/eu) for g, load in zip(available_bus, loads)]
    surplus = [max(0., g-local) for g, local in zip(available_bus, local_bus)]
    deficit = [max(0., load/eu-local) for load, local in zip(loads, local_bus)]
    outgoing, incoming = [0., 0.], [0., 0.]
    existing_send, link_send, direction = 0., 0., 0
    link_enabled = (policy != "conventional" and step.link_available and step.telemetry_fresh
                    and auxiliary_unmet <= TOL)
    path_caps = (min(params.conventional_capacity_w, params.conventional_receive_capacity_w/params.conventional_efficiency),
                 min(params.link_capacity_w, params.link_receive_capacity_w/params.link_efficiency) if link_enabled else 0.)
    path_etas = (params.conventional_efficiency, params.link_efficiency)
    for donor, receiver, sign in ((0, 1, 1), (1, 0, -1)):
        if surplus[donor] > TOL and deficit[receiver] > TOL:
            direction = sign
            if policy in ("conventional", "routed_restricted_optimizer"):
                flows = optimize_paths(surplus[donor], deficit[receiver], path_caps, path_etas)
            else:
                if policy == "routed_link_first":
                    order = (1, 0)
                elif policy == "routed_existing_first":
                    order = (0, 1)
                else:
                    order = tuple(sorted((0, 1), key=lambda i: (-path_etas[i], i)))
                flows = _ordered_paths(surplus[donor], deficit[receiver], path_caps, path_etas, order)
            existing_send, link_send = flows
            outgoing[donor] = sum(flows)
            incoming[receiver] = sum(f*eta for f, eta in zip(flows, path_etas))
            break
    if existing_send + link_send <= TOL:
        direction = 0
    raw_used = [(local+sent)/es for local, sent in zip(local_bus, outgoing)]
    load_bus = [local+received for local, received in zip(local_bus, incoming)]
    renewable_served = [bus*eu for bus in load_bus]
    grid = [max(0., min(cap, load-pv)) for cap, load, pv in zip(caps, loads, renewable_served)]
    served = [pv+grid_i for pv, grid_i in zip(renewable_served, grid)]
    unmet = [max(0., load-serve) for load, serve in zip(loads, served)]
    curtailed = [max(0., g-used) for g, used in zip(gs, raw_used)]
    source_loss = [used*(1-es) for used in raw_used]
    load_loss = [bus*(1-eu) for bus in load_bus]
    existing_loss = existing_send*(1-params.conventional_efficiency)
    link_loss = link_send*(1-params.link_efficiency)
    loss = sum(source_loss) + sum(load_loss) + existing_loss + link_loss
    row = {
        "policy": policy, "direction": direction,
        "link_enabled": link_enabled,
        "conventional_send_w": existing_send, "link_send_w": link_send,
        "conventional_signed_w": direction*existing_send, "link_signed_w": direction*link_send,
        "conventional_loss_w": existing_loss, "link_loss_w": link_loss,
        "total_available_pv_w": sum(gs), "total_demand_w": sum(loads),
        "total_pv_used_raw_w": sum(raw_used), "total_renewable_served_w": sum(renewable_served),
        "total_grid_import_w": sum(grid)+auxiliary_grid, "total_served_w": sum(served),
        "total_useful_grid_import_w": sum(grid),
        "auxiliary_requested_w": auxiliary_requested, "auxiliary_grid_w": auxiliary_grid,
        "auxiliary_unmet_w": auxiliary_unmet,
        "total_unmet_w": sum(unmet), "total_curtailment_w": sum(curtailed),
        "total_source_loss_w": sum(source_loss), "total_load_loss_w": sum(load_loss),
        "total_loss_w": loss,
        "service_status": "met" if sum(unmet)+auxiliary_unmet <= TOL else "policy_service_shortfall",
        "physical_infeasibility_proven": sum(gs)+step.grid_cap_a_w+step.grid_cap_b_w < sum(loads)+auxiliary_requested-TOL,
        "supply_lower_bound_shortfall_w": max(0.,sum(loads)+auxiliary_requested-sum(gs)-step.grid_cap_a_w-step.grid_cap_b_w),
        "balance_residual_w": sum(gs) + sum(grid)+auxiliary_grid - sum(served) - sum(curtailed) - loss-auxiliary_grid,
    }
    for i, label in enumerate(("a", "b")):
        for key, values in (("pv_available", gs), ("demand", loads), ("pv_used_raw", raw_used),
                            ("source_loss", source_loss), ("local_bus", local_bus),
                            ("incoming_bus", incoming), ("outgoing_bus", outgoing),
                            ("load_bus", load_bus), ("load_loss", load_loss),
                            ("renewable_served", renewable_served), ("grid_import", grid),
                            ("served", served), ("unmet", unmet), ("curtailment", curtailed)):
            row[f"{key}_{label}_w"] = values[i]
    return row


def audit(step: Step, params: Parameters, row: dict, tolerance=1e-7) -> list[str]:
    """Recompute physics-free accounting from primitive outputs; do not trust residual."""
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    for key, value in row.items():
        if key.endswith("_w"):
            check(math.isfinite(value), f"nonfinite {key}")
            if key not in ("conventional_signed_w", "link_signed_w", "balance_residual_w"):
                check(value >= -tolerance, f"negative {key}")
    check(row["direction"] in (-1, 0, 1), "invalid direction")
    check(abs(row["conventional_signed_w"]-row["direction"]*row["conventional_send_w"]) <= tolerance, "incorrect conventional signed flow")
    check(abs(row["link_signed_w"]-row["direction"]*row["link_send_w"]) <= tolerance, "incorrect link signed flow")
    check(row["conventional_send_w"] <= params.conventional_capacity_w+tolerance, "conventional rating exceeded")
    check(row["conventional_send_w"]*params.conventional_efficiency <= params.conventional_receive_capacity_w+tolerance, "conventional receiving rating exceeded")
    auxiliary_requested = params.auxiliary_standby_w if row["policy"] != "conventional" else 0.
    auxiliary_grid = min(auxiliary_requested, step.grid_cap_b_w)
    auxiliary_unmet = auxiliary_requested-auxiliary_grid
    check(abs(row["auxiliary_requested_w"]-auxiliary_requested) <= tolerance, "incorrect auxiliary demand")
    check(abs(row["auxiliary_grid_w"]-auxiliary_grid) <= tolerance, "incorrect auxiliary grid supply")
    check(abs(row["auxiliary_unmet_w"]-auxiliary_unmet) <= tolerance, "incorrect auxiliary unmet supply")
    enabled = (row["policy"] != "conventional" and step.link_available and step.telemetry_fresh
               and auxiliary_unmet <= TOL)
    check(row["link_enabled"] == enabled, "incorrect link enabled status")
    check(row["link_send_w"] <= (params.link_capacity_w if enabled else 0.)+tolerance, "link rating/fail-safe exceeded")
    check(row["link_send_w"]*params.link_efficiency <= params.link_receive_capacity_w+tolerance, "link receiving rating exceeded")
    check(row["conventional_signed_w"]*row["link_signed_w"] >= -tolerance, "opposing path flows")
    total_losses = row["conventional_loss_w"] + row["link_loss_w"]
    check(abs(row["conventional_loss_w"]-row["conventional_send_w"]*(1-params.conventional_efficiency)) <= tolerance, "existing loss inconsistent")
    check(abs(row["link_loss_w"]-row["link_send_w"]*(1-params.link_efficiency)) <= tolerance, "link loss inconsistent")
    for label, pv, demand, grid_cap in (("a", step.pv_a_w, step.load_a_w, step.grid_cap_a_w),
                                      ("b", step.pv_b_w, step.load_b_w, step.grid_cap_b_w)):
        raw = row[f"pv_used_raw_{label}_w"]
        source_loss = row[f"source_loss_{label}_w"]
        load_loss = row[f"load_loss_{label}_w"]
        outgoing = row[f"outgoing_bus_{label}_w"]
        incoming = row[f"incoming_bus_{label}_w"]
        load_bus = row[f"load_bus_{label}_w"]
        renewable = row[f"renewable_served_{label}_w"]
        grid = row[f"grid_import_{label}_w"]
        check(abs(row[f"pv_available_{label}_w"]-pv) <= tolerance, f"changed input PV {label}")
        check(abs(row[f"demand_{label}_w"]-demand) <= tolerance, f"changed input demand {label}")
        check(raw <= pv+tolerance, f"source budget {label}")
        check(abs(pv-raw-row[f"curtailment_{label}_w"]) <= tolerance, f"PV ledger {label}")
        check(abs(source_loss-raw*(1-params.source_efficiency)) <= tolerance, f"source conversion {label}")
        check(abs(load_loss-load_bus*(1-params.load_efficiency)) <= tolerance, f"load conversion {label}")
        check(abs(raw-source_loss+incoming-outgoing-load_bus) <= tolerance, f"bus balance {label}")
        check(abs(load_bus-load_loss-renewable) <= tolerance, f"load bus balance {label}")
        check(grid+(auxiliary_grid if label == "b" else 0.) <= grid_cap+tolerance, f"grid cap {label}")
        check(abs(renewable+grid-row[f"served_{label}_w"]) <= tolerance, f"double-counted service {label}")
        check(abs(demand-row[f"served_{label}_w"]-row[f"unmet_{label}_w"]) <= tolerance, f"useful demand balance {label}")
        total_losses += source_loss+load_loss
    total_send = row["conventional_send_w"]+row["link_send_w"]
    total_receive = row["conventional_send_w"]*params.conventional_efficiency+row["link_send_w"]*params.link_efficiency
    check(abs(row["outgoing_bus_a_w"]+row["outgoing_bus_b_w"]-total_send) <= tolerance, "outgoing cross-flow inconsistent")
    check(abs(row["incoming_bus_a_w"]+row["incoming_bus_b_w"]-total_receive) <= tolerance, "incoming cross-flow inconsistent")
    if row["direction"] == 1:
        check(row["outgoing_bus_b_w"] <= tolerance and row["incoming_bus_a_w"] <= tolerance, "A-to-B direction mismatch")
    elif row["direction"] == -1:
        check(row["outgoing_bus_a_w"] <= tolerance and row["incoming_bus_b_w"] <= tolerance, "B-to-A direction mismatch")
    else:
        check(total_send <= tolerance, "nonzero flow with zero direction")
    residual = (step.pv_a_w+step.pv_b_w+row["grid_import_a_w"]+row["grid_import_b_w"]
                -row["served_a_w"]-row["served_b_w"]-row["curtailment_a_w"]-row["curtailment_b_w"]-total_losses)
    check(abs(residual) <= tolerance, "global energy imbalance")
    check(abs(row["balance_residual_w"]-residual) <= tolerance, "reported residual inconsistent")
    for total, primitive in (("total_available_pv_w", "pv_available"), ("total_demand_w", "demand"),
                             ("total_pv_used_raw_w", "pv_used_raw"), ("total_renewable_served_w", "renewable_served"),
                             ("total_useful_grid_import_w", "grid_import"), ("total_served_w", "served"),
                             ("total_unmet_w", "unmet"), ("total_curtailment_w", "curtailment"),
                             ("total_source_loss_w", "source_loss"), ("total_load_loss_w", "load_loss")):
        check(abs(row[total]-row[f"{primitive}_a_w"]-row[f"{primitive}_b_w"]) <= tolerance, f"incorrect total {total}")
    check(abs(row["total_loss_w"]-total_losses) <= tolerance, "incorrect total loss")
    check(abs(row["total_grid_import_w"]-row["total_useful_grid_import_w"]-auxiliary_grid) <= tolerance, "incorrect total grid including auxiliary")
    check(row["service_status"] == ("met" if row["total_unmet_w"]+auxiliary_unmet <= TOL else "policy_service_shortfall"), "incorrect feasibility status")
    return errors
