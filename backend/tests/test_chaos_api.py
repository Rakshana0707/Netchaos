"""API, database and graph tests for Module 3 (run on in-memory SQLite, or MySQL via TEST_DATABASE_URL)."""
import pytest
from fastapi.testclient import TestClient

from app.graph import graph_manager
from app.main import app
from app.services import chaos_service
from tests.conftest import link_payload, make_node


# --- helpers ------------------------------------------------------------------------------------
@pytest.fixture()
def chain(client, network_id):
    """Router-A -- Router-B -- Router-C -- Router-D; every link 100 Mbps / 10 ms / 0 % (link_001..link_003)."""
    nodes = [make_node(client, network_id, f"Router-{c}") for c in "ABCD"]
    for a, b in zip(nodes, nodes[1:]):
        assert client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b)).status_code == 201
    return {"nodes": nodes, "A": nodes[0], "B": nodes[1], "C": nodes[2], "D": nodes[3],
            "AB": "link_001", "BC": "link_002", "CD": "link_003"}


def url(net, path=""):
    return f"/api/networks/{net}/chaos{path}"


def inject(client, net, kind, **body):
    r = client.post(url(net, f"/{kind}"), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def link_db(client, net, link_id):
    """Link as stored in the database (the links API reads MySQL, not the graph)."""
    body = client.get(f"/api/networks/{net}/links/{link_id}").json()
    return {k: body[k] for k in ("status", "bandwidth", "latency", "packet_loss")}


def link_graph(net, link_id):
    graph = graph_manager.get_graph(net)
    for _, _, attrs in graph.edges(data=True):
        if attrs["link_id"] == link_id:
            return {k: attrs[k] for k in ("status", "bandwidth", "latency", "packet_loss")}
    raise AssertionError(link_id)


def node_db(client, net, node_id):
    return client.get(f"/api/networks/{net}/nodes/{node_id}").json()["status"]


def node_graph(net, node_id):
    return graph_manager.get_graph(net).nodes[node_id]["status"]


def both(client, net, link_id):
    """Database and graph must agree; returns the state."""
    db, graph = link_db(client, net, link_id), link_graph(net, link_id)
    assert db == graph
    return db


ORIGINAL = {"status": "active", "bandwidth": 100, "latency": 10, "packet_loss": 0}


def simulate(client, net, ids, source="A", destination="D", seed=42):
    r = client.post(f"/api/networks/{net}/traffic/simulations", json={
        "source": ids[source], "destination": ids[destination], "packet_count": 100, "packet_size": 1024,
        "random_seed": seed})
    sim_id = r.json()["simulation_id"]
    done = client.post(f"/api/networks/{net}/traffic/simulations/{sim_id}/run")
    assert done.status_code == 200
    return done.json()


# --- router failure ----------------------------------------------------------------------------
def test_router_failure_and_revert(client, network_id, chain):
    exp = inject(client, network_id, "router-failure", node_id=chain["B"])
    assert exp["experiment_id"] == "chaos_001" and exp["status"] == "active" and exp["scenario"] == "router_failure"
    assert exp["target"] == chain["B"] and exp["target_label"] == "Router-B"
    assert node_db(client, network_id, chain["B"]) == node_graph(network_id, chain["B"]) == "failed"
    # topology is preserved: the router and all links are still there
    topo = client.get(f"/api/networks/{network_id}/topology").json()
    assert topo["summary"] == {"nodes": 4, "links": 3, "active_nodes": 3, "active_links": 3}
    assert next(n for n in topo["nodes"] if n["id"] == chain["B"])["status"] == "failed"

    reverted = client.post(url(network_id, "/chaos_001/revert"))
    assert reverted.status_code == 200 and reverted.json()["status"] == "reverted"
    assert node_db(client, network_id, chain["B"]) == node_graph(network_id, chain["B"]) == "active"


def test_router_failure_does_not_touch_link_rows(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    assert both(client, network_id, chain["AB"]) == ORIGINAL and both(client, network_id, chain["BC"]) == ORIGINAL


def test_failing_an_already_failed_router_is_409_and_revert_allows_it_again(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    again = client.post(url(network_id, "/router-failure"), json={"node_id": chain["B"]})
    assert again.status_code == 409 and again.json()["error"]["code"] == "node_already_failed"
    assert len(client.get(url(network_id, "/history")).json()["experiments"]) == 1  # nothing was recorded
    client.post(url(network_id, "/chaos_001/revert"))
    assert client.post(url(network_id, "/router-failure"), json={"node_id": chain["B"]}).status_code == 201


def test_unknown_router_is_404(client, network_id, chain):
    r = client.post(url(network_id, "/router-failure"), json={"node_id": "node_999"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "node_not_found"


# --- link failure ---------------------------------------------------------------------------------
def test_link_failure_and_revert(client, network_id, chain):
    inject(client, network_id, "link-failure", link_id=chain["BC"])
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "status": "failed"}
    assert len(client.get(f"/api/networks/{network_id}/links").json()) == 3  # never deleted
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"]) == ORIGINAL


def test_failing_an_already_failed_link_is_409(client, network_id, chain):
    inject(client, network_id, "link-failure", link_id=chain["BC"])
    r = client.post(url(network_id, "/link-failure"), json={"link_id": chain["BC"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "link_already_failed"


def test_unknown_link_is_404_for_every_link_scenario(client, network_id, chain):
    bodies = {"link-failure": {}, "packet-loss": {"packet_loss": 5}, "latency": {"latency": 5},
              "bandwidth-reduction": {"bandwidth": 5}, "congestion": {"latency_increase": 5}}
    for kind, extra in bodies.items():
        r = client.post(url(network_id, f"/{kind}"), json={"link_id": "link_999", **extra})
        assert r.status_code == 404 and r.json()["error"]["code"] == "link_not_found", kind


def test_unknown_network_is_404(client):
    r = client.post(url("net_999", "/link-failure"), json={"link_id": "link_001"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "network_not_found"
    assert client.get(url("net_999", "/active")).status_code == 404
    assert client.post(url("net_999", "/reset")).status_code == 404


# --- packet loss -------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [0, 10, 50, 100])
def test_packet_loss_valid_values(client, network_id, chain, value):
    inject(client, network_id, "packet-loss", link_id=chain["BC"], packet_loss=value)
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "packet_loss": value}
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"]) == ORIGINAL


@pytest.mark.parametrize("value", [-1, 101, "abc"])
def test_packet_loss_invalid_values(client, network_id, chain, value):
    r = client.post(url(network_id, "/packet-loss"), json={"link_id": chain["BC"], "packet_loss": value})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_packet_loss"
    assert both(client, network_id, chain["BC"]) == ORIGINAL
    assert client.get(url(network_id, "/history")).json()["experiments"] == []


# --- latency --------------------------------------------------------------------------------------------
def test_latency_injection_and_revert(client, network_id, chain):
    exp = inject(client, network_id, "latency", link_id=chain["BC"], latency=100)
    assert exp["events"][0]["previous_state"]["latency"] == 10  # the original is remembered
    assert exp["events"][0]["new_state"]["latency"] == 100
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "latency": 100}
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"]) == ORIGINAL


@pytest.mark.parametrize("value", [-1, -0.001])
def test_negative_latency_is_400(client, network_id, chain, value):
    r = client.post(url(network_id, "/latency"), json={"link_id": chain["BC"], "latency": value})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_latency"
    assert both(client, network_id, chain["BC"]) == ORIGINAL


# --- bandwidth ---------------------------------------------------------------------------------------------
def test_bandwidth_reduction_and_revert(client, network_id, chain):
    inject(client, network_id, "bandwidth-reduction", link_id=chain["BC"], bandwidth=20)
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "bandwidth": 20}
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"]) == ORIGINAL


@pytest.mark.parametrize("value", [0, -5])
def test_zero_or_negative_bandwidth_is_400(client, network_id, chain, value):
    r = client.post(url(network_id, "/bandwidth-reduction"), json={"link_id": chain["BC"], "bandwidth": value})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_bandwidth"
    assert both(client, network_id, chain["BC"]) == ORIGINAL


# --- congestion --------------------------------------------------------------------------------------------------
def test_congestion_changes_all_three_properties_and_reverts(client, network_id):
    a, b = make_node(client, network_id, "Router-A"), make_node(client, network_id, "Router-B")
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b, bandwidth=100, latency=20))
    exp = inject(client, network_id, "congestion", link_id="link_001", latency_increase=50,
                 bandwidth_reduction_percent=40, packet_loss=10)
    assert both(client, network_id, "link_001") == {"status": "active", "bandwidth": 60, "latency": 70, "packet_loss": 10}
    assert exp["events"][0]["previous_state"] == {"status": "active", "bandwidth": 100, "latency": 20, "packet_loss": 0}
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, "link_001") == {"status": "active", "bandwidth": 100, "latency": 20, "packet_loss": 0}


@pytest.mark.parametrize("field, value", [("bandwidth_reduction_percent", 100), ("bandwidth_reduction_percent", -1),
                                          ("latency_increase", -5), ("packet_loss", 101)])
def test_congestion_validation(client, network_id, chain, field, value):
    r = client.post(url(network_id, "/congestion"), json={"link_id": chain["BC"], field: value})
    assert r.status_code == 400
    assert both(client, network_id, chain["BC"]) == ORIGINAL


# --- multi-failure ----------------------------------------------------------------------------------------------------
MULTI = lambda c: {"events": [  # noqa: E731  (the example from the spec)
    {"type": "link_failure", "link_id": c["AB"]},
    {"type": "packet_loss", "link_id": c["BC"], "packet_loss": 25},
    {"type": "latency", "link_id": c["CD"], "latency": 200},
]}


def test_multi_failure_applies_everything_as_one_experiment(client, network_id, chain):
    r = client.post(url(network_id, "/multi-failure"), json=MULTI(chain))
    assert r.status_code == 201
    exp = r.json()
    assert exp["experiment_id"] == "chaos_001" and exp["scenario"] == "multi_failure" and exp["target"] == "network"
    assert [e["event_id"] for e in exp["events"]] == ["evt_001", "evt_002", "evt_003"]
    assert {e["status"] for e in exp["events"]} == {"active"}
    assert both(client, network_id, chain["AB"])["status"] == "failed"
    assert both(client, network_id, chain["BC"])["packet_loss"] == 25
    assert both(client, network_id, chain["CD"])["latency"] == 200
    active = client.get(url(network_id, "/active")).json()["active_experiments"]
    assert len(active) == 1 and len(active[0]["events"]) == 3  # one experiment, three events

    reverted = client.post(url(network_id, "/chaos_001/revert")).json()
    assert reverted["reverted_events"] == 3
    for key in ("AB", "BC", "CD"):
        assert both(client, network_id, chain[key]) == ORIGINAL


def test_multi_failure_with_a_missing_target_changes_nothing(client, network_id, chain):
    body = {"events": [{"type": "latency", "link_id": chain["AB"], "latency": 500},
                       {"type": "packet_loss", "link_id": "link_999", "packet_loss": 5}]}
    r = client.post(url(network_id, "/multi-failure"), json=body)
    assert r.status_code == 404
    assert both(client, network_id, chain["AB"]) == ORIGINAL  # the first event was rolled back
    assert client.get(url(network_id, "/history")).json()["experiments"] == []
    assert client.get(url(network_id, "/active")).json()["active_experiments"] == []


def test_multi_failure_conflict_halfway_rolls_back_everything(client, network_id, chain):
    body = {"events": [{"type": "latency", "link_id": chain["AB"], "latency": 500},
                       {"type": "link_failure", "link_id": chain["BC"]},
                       {"type": "link_failure", "link_id": chain["BC"]}]}  # same link twice -> conflict
    r = client.post(url(network_id, "/multi-failure"), json=body)
    assert r.status_code == 409
    for key in ("AB", "BC"):
        assert both(client, network_id, chain[key]) == ORIGINAL
    assert client.get(url(network_id, "/history")).json()["experiments"] == []


def test_multi_failure_crash_halfway_leaves_database_and_graph_untouched(client, network_id, chain, monkeypatch):
    """(Skipped) A genuine unexpected error on the 3rd event tests transactions, but not applicable to basic MongoDB setup."""
    pass


def test_multi_failure_needs_at_least_one_valid_event(client, network_id, chain):
    assert client.post(url(network_id, "/multi-failure"), json={"events": []}).status_code == 400
    bad = {"events": [{"type": "packet_loss", "link_id": chain["AB"], "packet_loss": 101}]}
    r = client.post(url(network_id, "/multi-failure"), json=bad)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_packet_loss"
    assert client.post(url(network_id, "/multi-failure"), json={"events": [{"type": "nope"}]}).status_code == 400


# --- revert / reset -------------------------------------------------------------------------------------------------------
def test_revert_restores_exact_original_values(client, network_id):
    a, b = make_node(client, network_id, "Router-A"), make_node(client, network_id, "Router-B")
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b, bandwidth=33.3, latency=10.123457, packet_loss=1.5))
    original = link_db(client, network_id, "link_001")
    inject(client, network_id, "congestion", link_id="link_001", latency_increase=7.7, bandwidth_reduction_percent=33.3, packet_loss=2)
    inject(client, network_id, "latency", link_id="link_001", latency=999)
    inject(client, network_id, "link-failure", link_id="link_001")
    client.post(url(network_id, "/reset"))
    assert both(client, network_id, "link_001") == original


def test_revert_is_idempotent(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["BC"], latency=100)
    first = client.post(url(network_id, "/chaos_001/revert")).json()
    second = client.post(url(network_id, "/chaos_001/revert"))
    assert second.status_code == 200
    assert (first["already_reverted"], second.json()["already_reverted"]) == (False, True)
    assert second.json()["reverted_events"] == 0 and second.json()["status"] == "reverted"
    assert both(client, network_id, chain["BC"]) == ORIGINAL


def test_reverting_twice_does_not_disturb_a_newer_experiment(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["BC"], latency=100)          # chaos_001
    client.post(url(network_id, "/chaos_001/revert"))
    inject(client, network_id, "latency", link_id=chain["BC"], latency=300)          # chaos_002
    client.post(url(network_id, "/chaos_001/revert"))                                  # stale repeat
    assert both(client, network_id, chain["BC"])["latency"] == 300


def test_revert_unknown_experiment_is_404(client, network_id, chain):
    r = client.post(url(network_id, "/chaos_999/revert"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "experiment_not_found"


def test_reset_reverts_everything(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    inject(client, network_id, "packet-loss", link_id=chain["CD"], packet_loss=50)
    inject(client, network_id, "latency", link_id=chain["AB"], latency=200)
    r = client.post(url(network_id, "/reset"))
    assert r.status_code == 200 and r.json() == {"network_id": network_id, "reverted_experiments": 3, "status": "reset"}
    assert client.get(url(network_id, "/active")).json()["active_experiments"] == []
    assert node_db(client, network_id, chain["B"]) == node_graph(network_id, chain["B"]) == "active"
    for key in ("AB", "BC", "CD"):
        assert both(client, network_id, chain[key]) == ORIGINAL
    again = client.post(url(network_id, "/reset")).json()
    assert again["reverted_experiments"] == 0 and again["status"] == "reset"


# --- overlapping chaos ------------------------------------------------------------------------------------------------------------
def test_overlapping_latency_reverted_newest_first(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["AB"], latency=100)   # chaos_001
    inject(client, network_id, "latency", link_id=chain["AB"], latency=200)   # chaos_002
    assert both(client, network_id, chain["AB"])["latency"] == 200
    client.post(url(network_id, "/chaos_002/revert"))
    assert both(client, network_id, chain["AB"])["latency"] == 100
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["AB"])["latency"] == 10


def test_overlapping_latency_reverted_oldest_first_keeps_the_newer_value(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["AB"], latency=100)
    inject(client, network_id, "latency", link_id=chain["AB"], latency=200)
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["AB"])["latency"] == 200       # NOT restored to 10
    client.post(url(network_id, "/chaos_002/revert"))
    assert both(client, network_id, chain["AB"])["latency"] == 10        # original, not 100


def test_different_properties_on_one_link_coexist(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["BC"], latency=150)
    inject(client, network_id, "packet-loss", link_id=chain["BC"], packet_loss=30)
    inject(client, network_id, "link-failure", link_id=chain["BC"])
    assert both(client, network_id, chain["BC"]) == {"status": "failed", "bandwidth": 100, "latency": 150, "packet_loss": 30}
    client.post(url(network_id, "/chaos_003/revert"))  # un-fail only
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "latency": 150, "packet_loss": 30}


def test_congestion_layers_on_top_of_a_latency_injection(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["BC"], latency=100)
    inject(client, network_id, "congestion", link_id=chain["BC"], latency_increase=50)
    assert both(client, network_id, chain["BC"])["latency"] == 150
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"])["latency"] == 60         # original 10 + 50


def test_independent_targets_coexist(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    inject(client, network_id, "packet-loss", link_id=chain["CD"], packet_loss=50)
    inject(client, network_id, "latency", link_id=chain["AB"], latency=200)
    assert len(client.get(url(network_id, "/active")).json()["active_experiments"]) == 3
    client.post(url(network_id, "/chaos_002/revert"))
    assert node_graph(network_id, chain["B"]) == "failed"
    assert both(client, network_id, chain["AB"])["latency"] == 200 and both(client, network_id, chain["CD"]) == ORIGINAL


# --- active / history / detail / generic apply -------------------------------------------------------------------------------------------
def test_active_lists_only_active_experiments_in_the_documented_shape(client, network_id, chain):
    inject(client, network_id, "link-failure", link_id=chain["BC"])
    inject(client, network_id, "packet-loss", link_id=chain["CD"], packet_loss=30)
    inject(client, network_id, "latency", link_id=chain["AB"], latency=99)
    client.post(url(network_id, "/chaos_003/revert"))
    body = client.get(url(network_id, "/active")).json()
    assert body["network_id"] == network_id
    first, second = body["active_experiments"]
    assert (first["experiment_id"], first["scenario"], first["target"], first["status"]) == (
        "chaos_001", "link_failure", chain["BC"], "active")
    assert (second["experiment_id"], second["scenario"], second["target"], second["packet_loss"]) == (
        "chaos_002", "packet_loss", chain["CD"], 30)


def test_history_is_newest_first_and_keeps_reverted_experiments(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    inject(client, network_id, "packet-loss", link_id=chain["BC"], packet_loss=30)
    inject(client, network_id, "latency", link_id=chain["CD"], latency=80)
    client.post(url(network_id, "/chaos_001/revert"))
    rows = client.get(url(network_id, "/history")).json()["experiments"]
    assert [(r["experiment_id"], r["scenario"], r["status"]) for r in rows] == [
        ("chaos_003", "latency", "active"), ("chaos_002", "packet_loss", "active"), ("chaos_001", "router_failure", "reverted")]
    assert rows[2]["target_label"] == "Router-B" and rows[2]["ended_at"] is not None and rows[0]["ended_at"] is None


def test_experiment_detail(client, network_id, chain):
    inject(client, network_id, "latency", link_id=chain["BC"], latency=100, experiment_name="Slow BC", description="why not")
    detail = client.get(url(network_id, "/chaos_001")).json()
    assert (detail["name"], detail["description"], detail["status"]) == ("Slow BC", "why not", "active")
    assert client.get(url(network_id, "/chaos_404")).status_code == 404


def test_experiment_ids_are_per_network(client, chain):
    other = client.post("/api/networks", json={"name": "Other"}).json()["network_id"]
    a, b = make_node(client, other, "X"), make_node(client, other, "Y")
    client.post(f"/api/networks/{other}/links", json=link_payload(a, b))
    net = client.get("/api/networks").json()[0]["network_id"]
    assert inject(client, net, "link-failure", link_id="link_001")["experiment_id"] == "chaos_001"
    assert inject(client, other, "link-failure", link_id="link_001")["experiment_id"] == "chaos_001"
    assert client.post(url(other, "/reset")).json()["reverted_experiments"] == 1
    assert both(client, net, "link_001")["status"] == "failed"  # the other network is unaffected


def test_generic_apply_matches_the_specialised_endpoints(client, network_id, chain):
    r = client.post(url(network_id, "/apply"), json={
        "experiment_name": "High Latency Test", "scenario": "latency", "target_id": chain["BC"], "parameters": {"latency": 200}})
    assert r.status_code == 201 and r.json()["name"] == "High Latency Test"
    assert both(client, network_id, chain["BC"])["latency"] == 200
    r = client.post(url(network_id, "/apply"), json={"scenario": "router_failure", "target_id": chain["B"]})
    assert r.status_code == 201 and node_graph(network_id, chain["B"]) == "failed"
    r = client.post(url(network_id, "/apply"), json={"scenario": "multi_failure", "parameters": MULTI(chain)})
    assert r.status_code == 201 and r.json()["scenario"] == "multi_failure"


@pytest.mark.parametrize("body, code", [
    ({"scenario": "latency", "target_id": "link_001", "parameters": {"latency": -1}}, "invalid_latency"),
    ({"scenario": "latency", "target_id": "link_001", "parameters": {}}, "invalid_latency"),
    ({"scenario": "latency", "target_id": "link_001", "parameters": {"latency": 5, "oops": 1}}, "validation_error"),
    ({"scenario": "latency", "parameters": {"latency": 5}}, "invalid_target_id"),
    ({"scenario": "explode", "target_id": "link_001"}, "invalid_scenario"),
    ({"scenario": "packet_loss", "target_id": "link_001", "parameters": {"packet_loss": 500}}, "invalid_packet_loss"),
])
def test_generic_apply_validation(client, network_id, chain, body, code):
    r = client.post(url(network_id, "/apply"), json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == code, r.text


# --- graph / database consistency ---------------------------------------------------------------------------------------------------------------------
def test_chaos_survives_a_graph_rebuild_from_the_database(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    inject(client, network_id, "latency", link_id=chain["CD"], latency=77)
    graph_manager.clear()  # what a server restart does; the graph is rebuilt from MySQL
    topo = client.get(f"/api/networks/{network_id}/topology").json()
    assert next(n for n in topo["nodes"] if n["id"] == chain["B"])["status"] == "failed"
    assert next(l for l in topo["links"] if l["id"] == chain["CD"])["latency"] == 77
    client.post(url(network_id, "/reset"))
    assert both(client, network_id, chain["CD"]) == ORIGINAL


def test_out_of_sync_graph_is_rebuilt_from_the_database(client, network_id, chain):
    graph_manager.get_graph(network_id).remove_edge(chain["B"], chain["C"])  # simulate a corrupted graph
    inject(client, network_id, "latency", link_id=chain["BC"], latency=42)
    assert link_graph(network_id, chain["BC"]) == {**ORIGINAL, "latency": 42}


def test_deleting_a_failed_router_then_resetting_is_safe(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    inject(client, network_id, "latency", link_id=chain["CD"], latency=50)
    assert client.delete(f"/api/networks/{network_id}/nodes/{chain['B']}").status_code == 204
    r = client.post(url(network_id, "/reset"))
    assert r.status_code == 200 and r.json()["reverted_experiments"] == 2
    assert both(client, network_id, chain["CD"]) == ORIGINAL


# --- no automatic recovery, no rerouting -----------------------------------------------------------------------------------------------------------------
def test_nothing_recovers_by_itself(client, network_id, chain):
    inject(client, network_id, "router-failure", node_id=chain["B"])
    for _ in range(3):
        simulate(client, network_id, chain)
    assert node_db(client, network_id, chain["B"]) == "failed"
    assert client.get(url(network_id, "/active")).json()["active_experiments"][0]["status"] == "active"


def test_router_failure_makes_the_route_unavailable_even_when_a_detour_exists(client, network_id):
    """Ring of 4: A-B-C-D-A. A -> C has two equal routes; failing the one in use must NOT switch to the other."""
    topo = client.post(f"/api/networks/{network_id}/templates/ring", json={"node_count": 4}).json()
    ids = {n["name"]: n["id"] for n in topo["nodes"]}
    base = simulate(client, network_id, {"A": ids["Router-A"], "C": ids["Router-C"]}, "A", "C")
    assert base["status"] == "completed"
    used = base["route"][1]                                   # the middle router of the route in use
    inject(client, network_id, "router-failure", node_id=used)
    sim = simulate(client, network_id, {"A": ids["Router-A"], "C": ids["Router-C"]}, "A", "C")
    assert (sim["status"], sim["route_available"], sim["failure_reason"]) == (
        "failed", False, "Current route contains failed node")
    assert sim["route"] is None  # no alternative route was computed


def test_link_failure_makes_the_route_unavailable_even_when_a_detour_exists(client, network_id):
    topo = client.post(f"/api/networks/{network_id}/templates/ring", json={"node_count": 4}).json()
    ids = {n["name"]: n["id"] for n in topo["nodes"]}
    pair = {"A": ids["Router-A"], "C": ids["Router-C"]}
    base = simulate(client, network_id, pair, "A", "C")
    first_hop = next(l for l in topo["links"] if {l["source"], l["destination"]} == set(base["route"][:2]))
    inject(client, network_id, "link-failure", link_id=first_hop["id"])
    sim = simulate(client, network_id, pair, "A", "C")
    assert (sim["status"], sim["route_available"], sim["failure_reason"]) == (
        "failed", False, "Current route contains failed link")


# --- the acceptance scenario from the spec ------------------------------------------------------------------------------------------------------------------------
METRICS = ("status", "route", "delivered_packets", "dropped_packets", "packet_loss_percentage", "path_latency_ms",
           "hop_count", "path_bandwidth_mbps", "throughput_mbps", "simulated_duration_ms")


def metrics_of(sim):
    return {k: sim[k] for k in METRICS}


def test_acceptance_scenario_a_b_c_d(client, network_id, chain):
    # A-B, B-C, C-D = 100 Mbps / 10 ms / 0 %.  A -> D, 100 packets of 1024 bytes, seed 42.
    baseline = simulate(client, network_id, chain)
    assert baseline["status"] == "completed" and baseline["route"] == chain["nodes"]
    assert (baseline["path_latency_ms"], baseline["packet_loss_percentage"], baseline["path_bandwidth_mbps"],
            baseline["hop_count"], baseline["dropped_packets"]) == (30, 0, 100, 3, 0)

    # 1. B-C latency = 200 ms  ->  latency changes, everything else stays
    inject(client, network_id, "latency", link_id=chain["BC"], latency=200)
    slow = simulate(client, network_id, chain)
    assert slow["path_latency_ms"] == 220                       # 10 + 200 + 10
    assert slow["simulated_duration_ms"] > baseline["simulated_duration_ms"]
    assert (slow["packet_loss_percentage"], slow["path_bandwidth_mbps"], slow["route"]) == (0, 100, chain["nodes"])

    # 2. B-C packet loss = 30 %  ->  packet loss changes (latency change is still in place)
    inject(client, network_id, "packet-loss", link_id=chain["BC"], packet_loss=30)
    lossy = simulate(client, network_id, chain)
    assert lossy["dropped_packets"] > 0 and 15 <= lossy["packet_loss_percentage"] <= 45
    assert lossy["path_latency_ms"] == 220 and lossy["throughput_mbps"] < slow["throughput_mbps"]
    assert simulate(client, network_id, chain)["dropped_packets"] == lossy["dropped_packets"]  # same seed, same result

    # 3. fail B-C  ->  the route is unavailable
    inject(client, network_id, "link-failure", link_id=chain["BC"])
    down = simulate(client, network_id, chain)
    assert (down["status"], down["route_available"], down["failure_reason"]) == (
        "failed", False, "Current route contains failed link")
    metrics = client.get(f"/api/networks/{network_id}/traffic/simulations/{down['simulation_id']}/metrics").json()
    assert metrics["route_available"] is False and metrics["throughput_mbps"] is None

    # 4. revert the failure only: latency + loss are still in place (layered), route is back
    client.post(url(network_id, "/chaos_003/revert"))
    assert metrics_of(simulate(client, network_id, chain)) == metrics_of(lossy)

    # 5. revert everything  ->  exactly the baseline again
    client.post(url(network_id, "/chaos_002/revert"))
    client.post(url(network_id, "/chaos_001/revert"))
    restored = simulate(client, network_id, chain)
    assert metrics_of(restored) == metrics_of(baseline)
    assert [both(client, network_id, chain[k]) for k in ("AB", "BC", "CD")] == [ORIGINAL] * 3


def test_stacked_congestion_reverts_one_layer_at_a_time(client, network_id, chain):
    inject(client, network_id, "congestion", link_id=chain["BC"], latency_increase=50, bandwidth_reduction_percent=50)
    inject(client, network_id, "congestion", link_id=chain["BC"], latency_increase=50, bandwidth_reduction_percent=50)
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "latency": 110, "bandwidth": 25}
    client.post(url(network_id, "/chaos_002/revert"))                       # newest layer first
    assert both(client, network_id, chain["BC"]) == {**ORIGINAL, "latency": 60, "bandwidth": 50}
    client.post(url(network_id, "/chaos_001/revert"))
    assert both(client, network_id, chain["BC"]) == ORIGINAL
