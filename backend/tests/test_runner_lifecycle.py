"""The batch runner must execute the real lifecycle and leave the network clean."""
import time
from tests.conftest import build_canonical


def _run(client, topo, chaos, **extra):
    n = topo["nodes"]
    plan = client.post("/api/experiment-plans", json={
        "name": "P", "network_id": topo["network_id"],
        "traffic": {"source": n["A"], "destination": n["D"], "packet_count": 100, "packet_size": 1024},
        "chaos": chaos, "recovery": {"enabled": True}, **extra}).json()
    pid = plan["plan_id"]
    assert client.post(f"/api/experiment-plans/{pid}/run").status_code < 300
    for _ in range(60):
        p = client.get(f"/api/experiment-plans/{pid}").json()
        if p["status"] not in ("CREATED", "RUNNING"):
            return p
        time.sleep(0.25)
    raise AssertionError("plan did not finish")


def test_runner_recovers_and_cleans_up(client):
    topo = build_canonical(client)
    plan = _run(client, topo, {"type": "link_failure", "target": topo["links"]["BD"]})
    assert plan["status"] == "COMPLETED", plan
    exp_id = plan["runs"][0]["experiment_id"]
    m = client.get(f"/api/experiments/{exp_id}").json()["metrics"]
    assert m["recovery_status"] == "recovered"
    assert m["phases"]["post_recovery"]["latency_ms"] == 40.0
    links = client.get(f"/api/networks/{topo['network_id']}/topology").json()["links"]
    assert all(link["status"] == "active" for link in links)
    results = client.get(f"/api/experiment-plans/{plan['plan_id']}/results").json()
    assert results["results"][0]["analytics"]["recoverable"] is True


def test_runner_unrecoverable(client):
    topo = build_canonical(client)
    plan = _run(client, topo, {"type": "router_failure", "target": topo["nodes"]["D"]})
    assert plan["status"] == "COMPLETED", plan
    m = client.get(f"/api/experiments/{plan['runs'][0]['experiment_id']}").json()["metrics"]
    assert m["recovery_status"] == "unrecoverable"


def test_runner_bad_target_fails_run_and_leaves_no_chaos(client):
    topo = build_canonical(client)
    plan = _run(client, topo, {"type": "link_failure", "target": "link_does_not_exist"})
    assert plan["status"] == "FAILED", plan
    assert plan["runs"][0]["status"] == "FAILED"
    links = client.get(f"/api/networks/{topo['network_id']}/topology").json()["links"]
    assert all(link["status"] == "active" for link in links)
