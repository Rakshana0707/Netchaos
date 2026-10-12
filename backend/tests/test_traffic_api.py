"""API + database tests for Module 2 (run on in-memory SQLite, or MySQL via TEST_DATABASE_URL)."""
import pytest
from app.database.database import get_mongo_db
from tests.conftest import link_payload, make_node


@pytest.fixture()
def chain(client, network_id):
    """Router-A -10ms/100- Router-B -20ms/50- Router-C -30ms/80- Server-D, no loss."""
    ids = [make_node(client, network_id, n, t) for n, t in
           [("Router-A", "router"), ("Router-B", "router"), ("Router-C", "router"), ("Server-D", "server")]]
    for (a, b), (bw, lat) in zip(zip(ids, ids[1:]), [(100, 10), (50, 20), (80, 30)]):
        r = client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b, bandwidth=bw, latency=lat))
        assert r.status_code == 201
    return ids


def base(network_id):
    return f"/api/networks/{network_id}/traffic/simulations"


def body(ids, **kw):
    return {"source": ids[0], "destination": ids[-1], "packet_count": 100, "packet_size": 1024, **kw}


def create(client, network_id, ids, **kw):
    r = client.post(base(network_id), json=body(ids, **kw))
    assert r.status_code == 201, r.text
    return r.json()


def run(client, network_id, sim_id):
    return client.post(f"{base(network_id)}/{sim_id}/run")


# --- creation ---------------------------------------------------------------------------------
def test_create_valid_simulation(client, network_id, chain):
    sim = create(client, network_id, chain, random_seed=42)
    assert sim["simulation_id"] == "sim_001" and sim["status"] == "pending"
    assert (sim["source"], sim["destination"]) == (chain[0], chain[-1])
    assert (sim["packet_count"], sim["packet_size"], sim["random_seed"]) == (100, 1024, 42)
    assert sim["route"] is None and sim["delivered_packets"] is None


def test_ids_are_sequential_per_network(client, network_id, chain):
    assert [create(client, network_id, chain)["simulation_id"] for _ in range(3)] == ["sim_001", "sim_002", "sim_003"]


def test_seed_is_generated_and_stored_when_omitted(client, network_id, chain):
    sim = create(client, network_id, chain)
    assert isinstance(sim["random_seed"], int)
    assert client.get(f"{base(network_id)}/sim_001").json()["random_seed"] == sim["random_seed"]


def test_nonexistent_network(client, chain):
    r = client.post(base("net_999"), json=body(chain))
    assert r.status_code == 404 and r.json()["error"]["code"] == "network_not_found"


def test_nonexistent_source_and_destination(client, network_id, chain):
    r = client.post(base(network_id), json=body(chain, source="node_999"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "node_not_found" and "Source" in r.json()["error"]["message"]
    r = client.post(base(network_id), json=body(chain, destination="node_999"))
    assert r.status_code == 404 and "Destination" in r.json()["error"]["message"]


def test_node_from_another_network_is_not_found(client, network_id, chain):
    other = client.post("/api/networks", json={"name": "Other"}).json()["network_id"]
    for name in ("V", "W", "X", "Y", "Z"):
        make_node(client, other, name)  # node_005 exists only in the other network
    r = client.post(base(network_id), json=body(chain, destination="node_005"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "node_not_found"


def test_source_equals_destination(client, network_id, chain):
    r = client.post(base(network_id), json=body(chain, destination=chain[0]))
    assert r.status_code == 400 and r.json()["error"]["code"] == "same_source_destination"


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"packet_count": 0}, "invalid_packet_count"), ({"packet_count": -5}, "invalid_packet_count"),
        ({"packet_count": 100_001}, "invalid_packet_count"), ({"packet_count": 1.5}, "invalid_packet_count"),
        ({"packet_size": 0}, "invalid_packet_size"), ({"packet_size": -1}, "invalid_packet_size"),
        ({"packet_size": 70_000}, "invalid_packet_size"), ({"random_seed": -1}, "invalid_random_seed"),
    ],
)
def test_invalid_parameters(client, network_id, chain, override, code):
    r = client.post(base(network_id), json=body(chain, **override))
    assert r.status_code == 400 and r.json()["error"]["code"] == code


def test_missing_field(client, network_id, chain):
    r = client.post(base(network_id), json={"source": chain[0]})
    assert r.status_code == 400 and "error" in r.json()


def test_store_packets_refused_for_large_simulations(client, network_id, chain):
    r = client.post(base(network_id), json=body(chain, packet_count=5000, store_packets=True))
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_store_packets"


# --- running ------------------------------------------------------------------------------------
def test_run_produces_correct_route_and_path_metrics(client, network_id, chain):
    create(client, network_id, chain, random_seed=42)
    r = run(client, network_id, "sim_001")
    assert r.status_code == 200
    sim = r.json()
    assert sim["status"] == "completed" and sim["route_available"] is True
    assert sim["route"] == chain
    assert sim["path_latency_ms"] == 60
    assert sim["hop_count"] == 3
    assert sim["path_bandwidth_mbps"] == 50
    assert sim["delivered_packets"] == 100 and sim["dropped_packets"] == 0
    assert sim["packet_loss_percentage"] == 0
    assert sim["started_at"] and sim["completed_at"]
    assert sim["simulated_duration_ms"] > 60 and sim["execution_duration_ms"] >= 0
    assert 0 < sim["throughput_mbps"] <= 50


def test_throughput_matches_delivered_data_and_duration(client, network_id, chain):
    create(client, network_id, chain, packet_count=500, packet_size=1500, random_seed=1)
    sim = run(client, network_id, "sim_001").json()
    expected = sim["delivered_packets"] * 1500 * 8 / (sim["simulated_duration_ms"] * 1000)
    assert sim["throughput_mbps"] == pytest.approx(expected, rel=1e-4)


def test_packet_loss_from_link_property_is_reproducible(client, network_id, chain):
    other = client.post("/api/networks", json={"name": "Lossy"}).json()["network_id"]
    ids = [make_node(client, other, n) for n in ("A", "B", "C")]
    client.post(f"/api/networks/{other}/links", json=link_payload(ids[0], ids[1], packet_loss=0))
    client.post(f"/api/networks/{other}/links", json=link_payload(ids[1], ids[2], packet_loss=10))
    results = []
    for _ in range(2):
        sid = client.post(base(other), json={"source": ids[0], "destination": ids[2], "packet_count": 2000,
                                              "packet_size": 500, "random_seed": 42}).json()["simulation_id"]
        results.append(client.post(f"{base(other)}/{sid}/run").json())
    assert results[0]["dropped_packets"] == results[1]["dropped_packets"] > 0
    assert results[0]["throughput_mbps"] == results[1]["throughput_mbps"]
    assert 8 < results[0]["packet_loss_percentage"] < 12


def test_no_route_gives_controlled_failure(client, network_id, chain):
    lonely = make_node(client, network_id, "Lonely")
    sim = client.post(base(network_id), json=body(chain, destination=lonely)).json()
    r = run(client, network_id, sim["simulation_id"])
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "failed" and out["route_available"] is False
    assert out["failure_reason"] == "No route available between source and destination"
    assert out["delivered_packets"] is None and out["throughput_mbps"] is None
    metrics = client.get(f"{base(network_id)}/{sim['simulation_id']}/metrics").json()
    assert metrics["status"] == "failed" and metrics["throughput_mbps"] is None


def test_run_uses_the_topology_as_it_is_at_run_time(client, network_id, chain):
    create(client, network_id, chain, random_seed=1)
    first = run(client, network_id, "sim_001").json()
    # change the topology in place (what Module 3 will do), then simulate again
    from app.graph import graph_manager
    graph_manager.get_graph(network_id)[chain[1]][chain[2]]["bandwidth"] = 5
    create(client, network_id, chain, random_seed=1)
    second = run(client, network_id, "sim_002").json()
    assert first["path_bandwidth_mbps"] == 50 and second["path_bandwidth_mbps"] == 5
    assert second["simulated_duration_ms"] > first["simulated_duration_ms"]
    # the earlier result is untouched
    assert client.get(f"{base(network_id)}/sim_001").json()["path_bandwidth_mbps"] == 50


def test_deleted_node_makes_a_pending_simulation_fail_when_run(client, network_id, chain):
    create(client, network_id, chain)
    client.delete(f"/api/networks/{network_id}/nodes/{chain[1]}")
    out = run(client, network_id, "sim_001").json()
    assert out["status"] == "failed" and out["failure_reason"]


def test_run_twice_is_refused_and_keeps_results(client, network_id, chain):
    create(client, network_id, chain, random_seed=3)
    first = run(client, network_id, "sim_001").json()
    r = run(client, network_id, "sim_001")
    assert r.status_code == 409 and r.json()["error"]["code"] == "simulation_already_finished"
    assert client.get(f"{base(network_id)}/sim_001").json()["throughput_mbps"] == first["throughput_mbps"]


def test_run_while_running_returns_409(client, network_id, chain):
    create(client, network_id, chain)
    db = next(get_mongo_db())
    db.traffic_simulations.update_one({"id": "sim_001", "network_id": network_id}, {"$set": {"status": "running"}})
    r = run(client, network_id, "sim_001")
    assert r.status_code == 409 and r.json()["error"]["code"] == "simulation_already_running"


def test_run_unknown_simulation_and_network(client, network_id, chain):
    assert run(client, network_id, "sim_099").status_code == 404
    assert client.post(f"{base('net_999')}/sim_001/run").status_code == 404


# --- reading ----------------------------------------------------------------------------------
def test_metrics_endpoint(client, network_id, chain):
    create(client, network_id, chain, random_seed=42)
    assert client.get(f"{base(network_id)}/sim_001/metrics").status_code == 409  # not run yet
    run(client, network_id, "sim_001")
    m = client.get(f"{base(network_id)}/sim_001/metrics").json()
    for key in ("packet_count", "delivered_packets", "dropped_packets", "packet_loss_percentage",
                "total_data_transferred_bytes", "path_latency_ms", "hop_count", "path_bandwidth_mbps",
                "throughput_mbps", "simulated_duration_ms", "execution_duration_ms"):
        assert m[key] is not None, key
    assert m["total_data_transferred_bytes"] == m["delivered_packets"] * 1024
    assert m["packet_count"] == m["delivered_packets"] + m["dropped_packets"]


def test_history_is_newest_first_and_get_one(client, network_id, chain):
    for _ in range(3):
        create(client, network_id, chain)
    run(client, network_id, "sim_002")
    history = client.get(base(network_id)).json()
    assert [s["simulation_id"] for s in history] == ["sim_003", "sim_002", "sim_001"]
    assert [s["status"] for s in history] == ["pending", "completed", "pending"]
    assert client.get(f"{base(network_id)}/sim_002").json()["status"] == "completed"
    assert client.get(f"{base(network_id)}/sim_099").status_code == 404
    assert client.get(base("net_999")).status_code == 404


def test_histories_are_separate_per_network(client, network_id, chain):
    create(client, network_id, chain)
    other = client.post("/api/networks", json={"name": "Other"}).json()["network_id"]
    assert client.get(base(other)).json() == []


# --- persistence ------------------------------------------------------------------------------
def test_results_persist_in_the_database(client, network_id, chain):
    create(client, network_id, chain, packet_count=250, packet_size=512, random_seed=9)
    api = run(client, network_id, "sim_001").json()
    db = next(get_mongo_db())
    row = db.traffic_simulations.find_one({"id": "sim_001", "network_id": network_id})
    assert row["status"] == "completed" and row["route"] == chain
    assert (row["packet_count"], row["packet_size"], row["random_seed"]) == (250, 512, 9)
    assert row["delivered_packets"] == api["delivered_packets"]
    assert row["throughput_mbps"] == api["throughput_mbps"]
    assert row["hop_count"] == 3 and row["path_bandwidth_mbps"] == 50 and row["path_latency_ms"] == 60
    assert row["simulated_duration_ms"] == api["simulated_duration_ms"]
    assert row.get("started_at") and row.get("completed_at")
    assert db.packets.count_documents({}) == 0


def test_history_survives_a_restart(client, network_id, chain):
    """Dropping the in-memory graph (as a restart does) must not affect stored simulations."""
    from app.graph import graph_manager
    create(client, network_id, chain, random_seed=5)
    before = run(client, network_id, "sim_001").json()
    graph_manager.clear()
    assert client.get(f"{base(network_id)}/sim_001").json() == before
    create(client, network_id, chain, random_seed=5)  # the graph is rebuilt from the database on demand
    again = run(client, network_id, "sim_002").json()
    assert again["route"] == chain and again["throughput_mbps"] == before["throughput_mbps"]


def test_deleting_a_node_keeps_simulation_history(client, network_id, chain):
    create(client, network_id, chain)
    run(client, network_id, "sim_001")
    client.delete(f"/api/networks/{network_id}/nodes/{chain[1]}")
    assert client.get(f"{base(network_id)}/sim_001").json()["status"] == "completed"


# --- optional packet records ----------------------------------------------------------------------
def test_packet_records_are_stored_only_when_requested(client, network_id, chain):
    create(client, network_id, chain, packet_count=200, store_packets=True, random_seed=42)
    run(client, network_id, "sim_001")
    page = client.get(f"{base(network_id)}/sim_001/packets?limit=50&offset=0").json()
    assert page["total"] == 200 and len(page["packets"]) == 50
    first = page["packets"][0]
    assert first["packet_id"] == "pkt_001" and first["sequence_number"] == 1
    assert first["status"] == "delivered" and first["route"] == chain and first["packet_size"] == 1024
    assert (first["source"], first["destination"]) == (chain[0], chain[-1])
    assert client.get(f"{base(network_id)}/sim_001/packets?offset=190&limit=50").json()["packets"][-1]["sequence_number"] == 200

    create(client, network_id, chain, packet_count=50)
    run(client, network_id, "sim_002")
    assert client.get(f"{base(network_id)}/sim_002/packets").json()["total"] == 0


def test_stored_packet_counts_match_simulation_totals(client, network_id):
    ids = [make_node(client, network_id, n) for n in ("A", "B")]
    client.post(f"/api/networks/{network_id}/links", json=link_payload(ids[0], ids[1], packet_loss=20))
    client.post(base(network_id), json={"source": ids[0], "destination": ids[1], "packet_count": 500,
                                        "packet_size": 100, "random_seed": 7, "store_packets": True})
    sim = run(client, network_id, "sim_001").json()
    packets = client.get(f"{base(network_id)}/sim_001/packets?limit=1000").json()["packets"]
    assert sum(p["status"] == "dropped" for p in packets) == sim["dropped_packets"] > 0
    assert sum(p["status"] == "delivered" for p in packets) == sim["delivered_packets"]
    assert all(p["dropped_at_link_id"] == "link_001" for p in packets if p["status"] == "dropped")


def test_10k_packet_simulation_stores_one_row_not_ten_thousand(client, network_id, chain):
    create(client, network_id, chain, packet_count=10_000, random_seed=1)
    out = run(client, network_id, "sim_001").json()
    assert out["status"] == "completed" and out["delivered_packets"] == 10_000
    db = next(get_mongo_db())
    assert db.traffic_simulations.count_documents({}) == 1
    assert db.packets.count_documents({}) == 0


def test_module1_templates_work_with_traffic(client, network_id):
    topo = client.post(f"/api/networks/{network_id}/templates/linear", json={"node_count": 5, "latency": 7}).json()
    ids = [n["id"] for n in topo["nodes"]]
    client.post(base(network_id), json={"source": ids[0], "destination": ids[-1], "packet_count": 10, "packet_size": 100})
    out = run(client, network_id, "sim_001").json()
    assert out["route"] == ids and out["hop_count"] == 4 and out["path_latency_ms"] == 28
