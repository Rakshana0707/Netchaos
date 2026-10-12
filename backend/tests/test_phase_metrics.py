"""Unit tests of the pure metric functions (no database)."""
import pytest
from app.analysis.phase_metrics import (compute_phase_metrics, resilience_score, interpret_resilience, impact_score)


def sim(lat=20.0, loss=0.0, thr=100.0, status="completed", route=("A", "B", "D")):
    return {"status": status, "path_latency_ms": lat, "packet_loss_percentage": loss,
            "throughput_mbps": thr, "route": list(route), "failure_reason": "down" if status == "failed" else None}


REC = {"recovery_status": "RECOVERED", "recovery_time_seconds": 2.0}


def test_recovered_flow():
    m = compute_phase_metrics(sim(), sim(status="failed", route=()), REC, sim(lat=40.0, thr=100.0))
    assert m["recovery_status"] == "recovered" and m["recoverable"]
    assert m["connectivity_during_chaos"] == 0.0 and m["connectivity_preservation"] == 100.0
    assert m["post_recovery_latency_degradation_percent"] == 100.0
    assert m["recovery_effectiveness_percent"] == 100.0
    assert m["latency_degradation_percent"] is None          # undefined while the flow was down
    # connectivity 0.30 + latency 0.20 + loss 0.20 + throughput 0.15 + recovery 0.15 * (2/10)
    assert m["impact_score"] == pytest.approx(0.30 + 0.20 + 0.20 + 0.15 + 0.15 * 0.2)
    assert m["data_complete"]


def test_unrecoverable_flow():
    m = compute_phase_metrics(sim(), sim(status="failed"), {"recovery_status": "NO_ALTERNATE_ROUTE"}, None)
    assert m["recovery_status"] == "unrecoverable" and not m["recoverable"]
    assert m["impact_score"] == 1.0
    assert m["recovery_effectiveness_percent"] == 0.0


def test_degradation_without_outage():
    m = compute_phase_metrics(sim(), sim(lat=40.0, loss=10.0, thr=50.0), None, None)
    assert m["recovery_status"] == "not_required"
    assert m["latency_degradation_percent"] == 100.0
    assert m["packet_loss_increase_points"] == 10.0
    assert m["throughput_degradation_percent"] == 50.0
    assert 0 < m["impact_score"] < 0.3


def test_missing_phases_are_none_not_zero():
    m = compute_phase_metrics(None, None, None, None)
    assert m["impact_score"] is None and m["connectivity_preservation"] is None
    assert not m["data_complete"] and m["missing"]


def test_down_flow_without_recovery_attempt():
    m = compute_phase_metrics(sim(), sim(status="failed"), None, None)
    assert m["recovery_status"] == "not_attempted"
    assert m["connectivity_preservation"] == 0.0


def test_scores_bounded_and_interpretation():
    assert resilience_score(100, 100) == 100 and resilience_score(0, 0) == 0
    assert interpret_resilience(95) == "Highly resilient" and interpret_resilience(10) == "Low resilience"
    huge = {"available": True}
    assert impact_score(huge, huge, 1e9, 1e9, 1e9, "recovered", 1e9) <= 1.0
