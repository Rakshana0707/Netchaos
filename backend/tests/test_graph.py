"""The NetworkX graph must always mirror what is stored in the database."""
import pytest

from app.graph import GraphError, GraphManager, graph_manager
from app.database.database import get_mongo_db
from tests.conftest import link_payload, make_node


def db_counts(network_id):
    db = next(get_mongo_db())
    nodes = db.nodes.count_documents({"network_id": network_id})
    links = db.links.count_documents({"network_id": network_id})
    return nodes, links


def assert_graph_matches_db(network_id):
    graph = graph_manager.get_graph(network_id)
    assert (graph.number_of_nodes(), graph.number_of_edges()) == db_counts(network_id)


def test_graph_tracks_adds_and_deletes(client, network_id):
    a = make_node(client, network_id, "Router-A")
    b = make_node(client, network_id, "Router-B")
    c = make_node(client, network_id, "Server-C", "server")
    assert_graph_matches_db(network_id)

    l1 = client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b)).json()["link_id"]
    client.post(f"/api/networks/{network_id}/links", json=link_payload(b, c))
    graph = graph_manager.get_graph(network_id)
    assert (graph.number_of_nodes(), graph.number_of_edges()) == (3, 2)
    assert graph.nodes[a]["type"] == "router" and graph.nodes[c]["type"] == "server"
    assert graph[a][b]["bandwidth"] == 100 and graph[a][b]["link_id"] == l1
    assert_graph_matches_db(network_id)

    client.delete(f"/api/networks/{network_id}/links/{l1}")
    assert_graph_matches_db(network_id)

    # deleting a node also removes its links, in the database and in the graph
    client.delete(f"/api/networks/{network_id}/nodes/{b}")
    assert db_counts(network_id) == (2, 0)
    assert_graph_matches_db(network_id)


def test_rejected_request_does_not_touch_graph(client, network_id):
    a = make_node(client, network_id, "Router-A")
    client.post(f"/api/networks/{network_id}/nodes", json={"name": "Router-A", "type": "router"})  # 409
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, "node_999"))  # 404
    assert_graph_matches_db(network_id)
    assert graph_manager.get_graph(network_id).number_of_nodes() == 1


def test_graph_is_rebuilt_from_database_after_restart(client, network_id):
    a = make_node(client, network_id, "Router-A")
    b = make_node(client, network_id, "Router-B")
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b, latency=25))
    before = client.get(f"/api/networks/{network_id}/topology").json()

    graph_manager.clear()  # what a server restart does to the in-memory state
    assert not graph_manager.has_graph(network_id)

    assert client.get(f"/api/networks/{network_id}/topology").json() == before
    assert graph_manager.get_graph(network_id)[a][b]["latency"] == 25


def test_edit_after_restart_keeps_graph_in_sync(client, network_id):
    a = make_node(client, network_id, "Router-A")
    graph_manager.clear()
    b = make_node(client, network_id, "Router-B")  # must load existing node A before adding B
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b))
    assert_graph_matches_db(network_id)
    assert graph_manager.get_graph(network_id).number_of_nodes() == 2


def test_topology_endpoint(client, network_id):
    a = make_node(client, network_id, "Router-A")
    b = make_node(client, network_id, "Client-B", "client")
    client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b))
    body = client.get(f"/api/networks/{network_id}/topology").json()
    assert body["network_id"] == network_id
    assert body["nodes"][0] == {"id": a, "name": "Router-A", "type": "router", "status": "active"}
    assert body["links"][0]["id"] == "link_001"
    assert body["summary"] == {"nodes": 2, "links": 1, "active_nodes": 2, "active_links": 1}


def test_topology_of_missing_network(client):
    assert client.get("/api/networks/net_999/topology").status_code == 404


class TestGraphManagerAlone:
    def test_rejects_invalid_operations(self):
        manager = GraphManager()
        manager.create_graph("n")
        manager.add_node("n", "a")
        manager.add_node("n", "b")
        manager.add_link("n", "l1", "a", "b", bandwidth=1)
        with pytest.raises(GraphError):
            manager.add_node("n", "a")
        with pytest.raises(GraphError):
            manager.add_link("n", "l2", "b", "a")  # duplicate, other direction
        with pytest.raises(GraphError):
            manager.add_link("n", "l3", "a", "zzz")
        with pytest.raises(GraphError):
            manager.remove_link("n", "nope")
        with pytest.raises(GraphError):
            manager.get_graph("other")

    def test_lists(self):
        manager = GraphManager()
        manager.create_graph("n")
        manager.add_node("n", "a", name="A")
        manager.add_node("n", "b", name="B")
        manager.add_link("n", "l1", "a", "b", latency=5)
        assert [n["node_id"] for n in manager.get_nodes("n")] == ["a", "b"]
        assert manager.get_links("n") == [{"source": "a", "destination": "b", "link_id": "l1", "latency": 5}]
