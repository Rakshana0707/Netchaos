"""Pure chaos state maths (Module 3). No FastAPI, SQLAlchemy or NetworkX imports.

State-management strategy: **recompute the effective state from the active chaos events.**

Every node/link has a *baseline* (its configuration before any active chaos touched it). Each active
chaos event is a small, deterministic operator. The effective state of a target is

    effective = fold(apply_event, baseline, active events on that target, oldest first)

so overlapping experiments layer on top of each other, and reverting any one of them simply drops
its operator and recomputes. Nothing is ever "restored" by writing an old value back on top of a newer one.

Operators:
  router_failure / link_failure   status := failed
  packet_loss                     packet_loss := value                                   (absolute)
  latency                         latency := value                                       (absolute)
  bandwidth_reduction             bandwidth := value                                     (absolute)
  congestion                      latency += latency_increase
                                  bandwidth := bandwidth * (100 - bandwidth_reduction_percent) / 100
                                  packet_loss := min(100, packet_loss + packet_loss)     (relative)

Absolute operators: the latest active one wins. Relative operators (congestion) stack on whatever is below
them in the layer order. Results are rounded to 6 decimals so every calculation is exactly reproducible.
"""
from collections.abc import Iterable, Mapping
from typing import Any

from app.enums import ElementStatus, ScenarioType, TargetType

LINK_FIELDS = ("status", "bandwidth", "latency", "packet_loss")
NODE_FIELDS = ("status",)

_FAILED = ElementStatus.FAILED.value
_ROUND = 6


def state_fields(target_type: TargetType | str) -> tuple[str, ...]:
    return NODE_FIELDS if TargetType(target_type) is TargetType.NODE else LINK_FIELDS


def snapshot(target_type: TargetType | str, source: Any) -> dict[str, Any]:
    """Plain-dict copy of a node's or link's state (``source`` is a model row or a mapping)."""
    get = source.get if isinstance(source, Mapping) else lambda name: getattr(source, name)
    return {name: get(name) for name in state_fields(target_type)}


def apply_event(state: Mapping[str, Any], scenario: ScenarioType | str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``state`` with one chaos operator applied. Never mutates its input."""
    scenario = ScenarioType(scenario)
    new = dict(state)
    if scenario in (ScenarioType.ROUTER_FAILURE, ScenarioType.LINK_FAILURE):
        new["status"] = _FAILED
    elif scenario is ScenarioType.PACKET_LOSS:
        new["packet_loss"] = float(parameters["packet_loss"])
    elif scenario is ScenarioType.LATENCY:
        new["latency"] = float(parameters["latency"])
    elif scenario is ScenarioType.BANDWIDTH_REDUCTION:
        new["bandwidth"] = float(parameters["bandwidth"])
    elif scenario is ScenarioType.CONGESTION:
        new["latency"] = round(new["latency"] + float(parameters.get("latency_increase", 0)), _ROUND)
        percent = float(parameters.get("bandwidth_reduction_percent", 0))
        new["bandwidth"] = round(new["bandwidth"] * (100.0 - percent) / 100.0, _ROUND)
        new["packet_loss"] = round(min(100.0, new["packet_loss"] + float(parameters.get("packet_loss", 0))), _ROUND)
    else:  # multi_failure is expanded into child events before it gets here
        raise ValueError(f"'{scenario.value}' is not a state-changing operator")
    return new


def effective_state(baseline: Mapping[str, Any], events: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Fold ``(scenario, parameters)`` operators, oldest first, over ``baseline``."""
    state = dict(baseline)
    for scenario, parameters in events:
        state = apply_event(state, scenario, parameters)
    return state
