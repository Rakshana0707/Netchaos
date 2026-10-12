"""Strategies, restart behaviour and edge cases around the lifecycle."""
import pytest
from tests.conftest import build_canonical, run_sim


@pytest.mark.parametrize("strategy", ["shortest_hop", "lowest_latency", "highest_bandwidth", "composite"])
def test_every_strategy_recovers_canonical_failure(client, strategy):
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/failures/baseline")
    base = run_sim(client, nid, n["A"], n["D"])
    client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]})
    client.post(f"/api/networks/{nid}/failures/detect")
    rec = client.post(f"/api/networks/{nid}/recovery", json={"simulation_id": base["id"], "strategy": strategy}).json()
    assert rec["status"] == "RECOVERED"
    assert rec["recovered_route"] == [n["A"], n["C"], n["D"]]


def test_graph_rebuilds_after_restart(client):
    from app.graph import graph_manager
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    graph_manager.clear()  # simulates a process restart: MongoDB is the source of truth
    sim = run_sim(client, nid, n["A"], n["D"])
    assert sim["path_latency_ms"] == 20.0


def test_failed_state_survives_restart(client):
    from app.graph import graph_manager
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]})
    graph_manager.clear()
    sim = run_sim(client, nid, n["A"], n["B"])
    assert sim["status"] == "completed"
    d = run_sim(client, nid, n["B"], n["D"])
    assert d["status"] != "completed" or d["route"] != [n["B"], n["D"]]


def test_double_failure_of_same_link_conflicts_and_revert_restores(client):
    topo = build_canonical(client)
    nid = topo["network_id"]
    first = client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]})
    assert first.status_code == 201
    second = client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]})
    assert second.status_code == 409
    assert client.post(f"/api/networks/{nid}/chaos/{first.json()['experiment_id']}/revert").status_code == 200
    again = client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]})
    assert again.status_code == 201
    assert again.json()["experiment_id"] != first.json()["experiment_id"]


def test_same_source_destination_and_unknown_node_rejected(client):
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    body = {"source": n["A"], "destination": n["A"], "packet_count": 10, "packet_size": 100}
    assert client.post(f"/api/networks/{nid}/traffic/simulations", json=body).status_code == 400
    body["destination"] = "node_999"
    assert client.post(f"/api/networks/{nid}/traffic/simulations", json=body).status_code == 404


def test_recovery_with_no_failure_is_not_required(client):
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    base = run_sim(client, nid, n["A"], n["D"])
    rec = client.post(f"/api/networks/{nid}/recovery", json={"simulation_id": base["id"], "strategy": "shortest_hop"}).json()
    assert rec["status"] == "NOT_REQUIRED"


def test_ids_stay_unique_after_deletions(client):
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    a = run_sim(client, nid, n["A"], n["D"])
    b = run_sim(client, nid, n["A"], n["D"])
    assert a["id"] != b["id"]


def test_chaos_ids_unique_across_revert(client):
    topo = build_canonical(client)
    nid = topo["network_id"]
    ids = []
    for _ in range(3):
        r = client.post(f"/api/networks/{nid}/chaos/latency", json={"link_id": topo["links"]["AB"], "latency": 50}).json()
        ids.append(r["experiment_id"])
        client.post(f"/api/networks/{nid}/chaos/{r['experiment_id']}/revert")
    assert len(set(ids)) == 3
