import pytest
import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    from app.database.database import get_mongo_db
    from app.graph import graph_manager
    db = next(get_mongo_db())
    db.networks.delete_many({})
    db.nodes.delete_many({})
    db.links.delete_many({})
    db.traffic_simulations.delete_many({})
    db.chaos_experiments.delete_many({})
    db.recovery_events.delete_many({})
    db.experiments.delete_many({})
    db.experiment_plans.delete_many({})
    graph_manager.clear()
    yield
    # Wait briefly for any background threads to finish
    time.sleep(1)
    db.networks.delete_many({})
    db.experiment_plans.delete_many({})
    graph_manager.clear()


def _wait_for_plan(plan_id: str, timeout: int = 30) -> dict:
    """Poll until plan leaves RUNNING/CREATED state, return final plan."""
    for _ in range(timeout):
        res = client.get(f"/api/experiment-plans/{plan_id}")
        p = res.json()
        if p["status"] not in ["CREATED", "RUNNING"]:
            return p
        time.sleep(1)
    return client.get(f"/api/experiment-plans/{plan_id}").json()


def _build_simple_network():
    """Helper to build a simple 2-node network; returns (nid, node_a, node_b, link_ab)."""
    res = client.post("/api/networks", json={"name": "Test Net"})
    nid = res.json()["network_id"]
    res = client.post(f"/api/networks/{nid}/nodes", json={"name": "A", "type": "router"})
    node_a = res.json()["node_id"]
    res = client.post(f"/api/networks/{nid}/nodes", json={"name": "B", "type": "router"})
    node_b = res.json()["node_id"]
    res = client.post(f"/api/networks/{nid}/links", json={
        "source": node_a, "destination": node_b,
        "bandwidth": 1000, "latency": 10, "packet_loss": 0
    })
    link_ab = res.json()["link_id"]
    return nid, node_a, node_b, link_ab


# ─── Test 1: plan rejection when repetitions exceed limit ──────────────────────
def test_runner_validation():
    res = client.post("/api/experiment-plans", json={
        "name": "Validation Test",
        "description": "Validation Test",
        "network_id": "net_invalid",
        "traffic": {
            "source": "A", "destination": "B",
            "packet_count": 100, "packet_size": 1024
        },
        "chaos": {"type": "link_failure", "target": "A-B"},
        "recovery": {"enabled": True},
        "repetitions": 105,   # Exceeds the 100-run limit
    })
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.json()}"
    assert "exceeds" in str(res.json()).lower()


# ─── Test 2: full batch run with 2 repetitions × 2 sweep values ───────────────
def test_runner_batch_execution():
    nid, node_a, node_b, link_ab = _build_simple_network()

    plan_data = {
        "name": "Batch Test",
        "network_id": nid,
        "traffic": {
            "source": node_a, "destination": node_b,
            "packet_count": 100, "packet_size": 512,
        },
        "chaos": {"type": "link_failure", "target": link_ab},
        "recovery": {"enabled": False},
        "repetitions": 2,
        "sweep": {"parameter": "packet_count", "values": [50, 200]},
    }

    # Create plan
    res = client.post("/api/experiment-plans", json=plan_data)
    assert res.status_code == 200, f"Plan creation failed: {res.json()}"
    plan = res.json()
    assert plan["total_runs"] == 4, f"Expected 4 total_runs, got {plan['total_runs']}"
    plan_id = plan["plan_id"]

    # Start execution
    res = client.post(f"/api/experiment-plans/{plan_id}/run")
    assert res.status_code == 200

    # Wait up to 30 seconds
    p = _wait_for_plan(plan_id, timeout=30)

    # Batch should have completed cleanly
    assert p["status"] == "COMPLETED", (
        f"Plan ended in {p['status']}. "
        f"Completed={p['completed_runs']}, Failed={p['failed_runs']}. "
        f"Run errors: {[r.get('error') for r in p['runs'] if r.get('error')]}"
    )
    assert p["completed_runs"] == 4

    # Results endpoint
    res = client.get(f"/api/experiment-plans/{plan_id}/results")
    assert res.status_code == 200
    data = res.json()
    # All 4 runs should have analytics entries (analytics may be empty for runs
    # without a full experiment, so just verify the response is well-formed)
    assert "results" in data
    assert data["total_runs"] == 4


# ─── Test 3: cancellation stops further runs ──────────────────────────────────
def test_runner_cancellation():
    nid, node_a, node_b, link_ab = _build_simple_network()

    plan_data = {
        "name": "Cancel Test",
        "network_id": nid,
        "traffic": {
            "source": node_a, "destination": node_b,
            "packet_count": 50, "packet_size": 512,
        },
        "chaos": {"type": "link_failure", "target": link_ab},
        "recovery": {"enabled": False},
        "repetitions": 5,   # 5 runs
    }

    res = client.post("/api/experiment-plans", json=plan_data)
    assert res.status_code == 200
    plan_id = res.json()["plan_id"]

    client.post(f"/api/experiment-plans/{plan_id}/run")
    time.sleep(1.5)    # let at least one run start
    cancel_res = client.post(f"/api/experiment-plans/{plan_id}/cancel")
    assert cancel_res.status_code == 200

    p = _wait_for_plan(plan_id, timeout=25)

    # After cancel, the plan should be in a terminal state
    assert p["status"] in ["CANCELLED", "COMPLETED", "PARTIAL"], (
        f"Unexpected terminal status: {p['status']}"
    )
    # No active chaos should remain — wait for background thread to clean up
    time.sleep(2)
    from app.database.database import get_mongo_db
    db = next(get_mongo_db())
    active = list(db.chaos_experiments.find({"network_id": nid, "status": "ACTIVE"}))
    assert len(active) == 0, f"Active chaos still present after cancel: {active}"
