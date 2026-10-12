"""Experiment metrics computed from the four lifecycle phases of ONE traffic flow.

    BASELINE (healthy)  ->  CHAOS (failure injected)  ->  RECOVERY (alternative route)  ->  POST-RECOVERY

Everything here is a pure function of stored simulation / recovery records: no database access, no
defaults that pretend data exists. A metric that cannot be derived from what was recorded is ``None`` and
the reason is listed in ``missing``. All values are *simulated* (simulated latency, loss and throughput;
recovery time is simulator wall-clock) and are internal project indicators, not network benchmarks.
"""
from __future__ import annotations

from typing import Any, Mapping

# Weights of the impact score (ANALYTICS.md). They sum to 1.0, so the score lies in [0, 1].
IMPACT_WEIGHTS = {"connectivity": 0.30, "latency": 0.20, "packet_loss": 0.20, "throughput": 0.15, "recovery": 0.15}
LATENCY_CAP_PERCENT = 1000.0      # latency increase that counts as the maximum latency impact
RECOVERY_TIME_CAP_SECONDS = 10.0  # recovery interval that counts as the maximum recovery impact

RECOVERED, NOT_REQUIRED, UNRECOVERABLE, NOT_ATTEMPTED, UNKNOWN = (
    "recovered", "not_required", "unrecoverable", "not_attempted", "unknown",
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def flow_view(sim: Mapping[str, Any] | None) -> dict | None:
    """Normalise one stored simulation into the numbers analytics needs (None if the phase was not run).

    A simulation that failed because its route was unavailable is a flow that is DOWN: nothing was
    delivered, so loss is 100 % and throughput 0 (latency is undefined).
    """
    if sim is None or sim.get("status") not in ("completed", "failed"):
        return None
    if sim["status"] == "failed":
        return {"available": False, "latency_ms": None, "packet_loss_percent": 100.0,
                "throughput_mbps": 0.0, "route": sim.get("route") or [], "reason": sim.get("failure_reason")}
    return {"available": True, "latency_ms": sim.get("path_latency_ms"),
            "packet_loss_percent": sim.get("packet_loss_percentage") or 0.0,
            "throughput_mbps": sim.get("throughput_mbps") or 0.0, "route": sim.get("route") or [], "reason": None}


def recovery_status(chaos: dict | None, recovery: Mapping[str, Any] | None) -> str:
    if chaos is None:
        return UNKNOWN
    if chaos["available"]:
        return NOT_REQUIRED          # the flow's route survived the chaos, nothing needed recovering
    status = (recovery or {}).get("recovery_status")
    if status == "RECOVERED":
        return RECOVERED
    if status == "NO_ALTERNATE_ROUTE":
        return UNRECOVERABLE
    if status == "NOT_REQUIRED":
        return NOT_REQUIRED
    return NOT_ATTEMPTED


def _pct_change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return (after - before) / before * 100.0


def compute_phase_metrics(
    baseline_sim: Mapping[str, Any] | None, chaos_sim: Mapping[str, Any] | None,
    recovery: Mapping[str, Any] | None, post_sim: Mapping[str, Any] | None,
) -> dict:
    b, c, p = flow_view(baseline_sim), flow_view(chaos_sim), flow_view(post_sim)
    missing: list[str] = []
    if b is None:
        missing.append("baseline simulation")
    elif not b["available"]:
        missing.append("baseline simulation (route was already unavailable)")
        b = None
    if c is None:
        missing.append("chaos-phase simulation")
    status = recovery_status(c, recovery)

    conn_chaos = None if c is None else (100.0 if c["available"] else 0.0)
    if status in (NOT_REQUIRED, RECOVERED) and not (status == RECOVERED and p is not None and not p["available"]):
        conn_kept: float | None = 100.0
    elif status == UNKNOWN:
        conn_kept = None
    else:
        conn_kept = 0.0

    lat_deg = thr_deg = loss_inc = post_lat_deg = None
    if b and c:
        loss_inc = c["packet_loss_percent"] - b["packet_loss_percent"]
        thr_deg = _pct_change(b["throughput_mbps"], c["throughput_mbps"])
        thr_deg = None if thr_deg is None else -thr_deg          # positive number = throughput lost
        lat_deg = _pct_change(b["latency_ms"], c["latency_ms"]) if c["available"] else None
    if b and p and p["available"]:
        post_lat_deg = _pct_change(b["latency_ms"], p["latency_ms"])

    effectiveness = None
    if status == UNRECOVERABLE:
        effectiveness = 0.0
    elif status == RECOVERED and b and c and p:
        if not p["available"]:
            effectiveness = 0.0
        elif b["throughput_mbps"] > c["throughput_mbps"]:
            effectiveness = _clamp((p["throughput_mbps"] - c["throughput_mbps"])
                                   / (b["throughput_mbps"] - c["throughput_mbps"]), 0, 1) * 100.0
        else:
            effectiveness = 100.0

    recovery_time = (recovery or {}).get("recovery_time_seconds") if status == RECOVERED else None
    if status == RECOVERED and recovery_time is None:
        missing.append("recovery time (no failure detection was recorded before recovery)")
    if status == NOT_ATTEMPTED:
        missing.append("recovery attempt")

    return {
        "phases": {"baseline": b, "chaos": c, "post_recovery": p},
        "recovery_status": status,
        "recoverable": status in (NOT_REQUIRED, RECOVERED),
        "connectivity_during_chaos": conn_chaos,
        "connectivity_preservation": conn_kept,
        "latency_degradation_percent": lat_deg,
        "post_recovery_latency_degradation_percent": post_lat_deg,
        "packet_loss_increase_points": loss_inc,
        "throughput_degradation_percent": thr_deg,
        "recovery_effectiveness_percent": effectiveness,
        "recovery_time_seconds": recovery_time,
        "impact_score": impact_score(c, b, lat_deg, loss_inc, thr_deg, status, recovery_time),
        "data_complete": not missing,
        "missing": missing,
    }


def impact_score(
    chaos: dict | None, baseline: dict | None, lat_deg: float | None, loss_inc: float | None,
    thr_deg: float | None, status: str, recovery_time: float | None,
) -> float | None:
    """Weighted damage index in [0, 1] (0 = no impact). See ANALYTICS.md for the weights."""
    if chaos is None or baseline is None:
        return None
    down = not chaos["available"]
    parts = {
        "connectivity": 1.0 if down else 0.0,
        "latency": 1.0 if down else _clamp((lat_deg or 0.0) / LATENCY_CAP_PERCENT),
        "packet_loss": 1.0 if down else _clamp((loss_inc or 0.0) / 100.0),
        "throughput": 1.0 if down else _clamp((thr_deg or 0.0) / 100.0),
        "recovery": (0.0 if status == NOT_REQUIRED
                     else _clamp((recovery_time or 0.0) / RECOVERY_TIME_CAP_SECONDS) if status == RECOVERED
                     else 1.0),
    }
    return round(sum(IMPACT_WEIGHTS[k] * v for k, v in parts.items()), 4)


def resilience_score(avg_connectivity: float, recoverability_percent: float) -> float:
    """0-100 internal indicator: equal weight on connectivity kept and share of failures recovered.

    ANALYTICS.md originally weighted these 0.4 + 0.4, which capped the score at 80; the weights are
    normalised to 0.5 + 0.5 so a fully resilient network scores 100.
    """
    return round(0.5 * avg_connectivity + 0.5 * recoverability_percent, 2)


def interpret_resilience(score: float) -> str:
    if score >= 90:
        return "Highly resilient"
    if score >= 75:
        return "Resilient"
    if score >= 50:
        return "Moderately resilient"
    return "Low resilience"
