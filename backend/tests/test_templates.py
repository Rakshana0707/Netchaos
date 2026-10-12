import pytest

from app.graph import graph_manager
from tests.conftest import make_node

# template -> (default nodes, default links)
EXPECTED = {"linear": (4, 3), "star": (5, 4), "ring": (4, 4), "mesh": (4, 6)}


@pytest.mark.parametrize("template", EXPECTED)
def test_template_creates_expected_topology(client, network_id, template):
    response = client.post(f"/api/networks/{network_id}/templates/{template}")
    assert response.status_code == 201
    nodes, links = EXPECTED[template]
    assert response.json()["summary"] == {"nodes": nodes, "links": links, "active_nodes": nodes, "active_links": links}

    # persisted in the database...
    assert len(client.get(f"/api/networks/{network_id}/nodes").json()) == nodes
    assert len(client.get(f"/api/networks/{network_id}/links").json()) == links
    # ...and represented in NetworkX
    graph = graph_manager.get_graph(network_id)
    assert (graph.number_of_nodes(), graph.number_of_edges()) == (nodes, links)


def test_linear_shape_and_star_hub(client, network_id):
    body = client.post(f"/api/networks/{network_id}/templates/linear").json()
    assert [n["type"] for n in body["nodes"]] == ["client", "router", "router", "server"]
    assert [(l["source"], l["destination"]) for l in body["links"]] == [
        ("node_001", "node_002"), ("node_002", "node_003"), ("node_003", "node_004"),
    ]

    star_net = client.post("/api/networks", json={"name": "S"}).json()["network_id"]
    star = client.post(f"/api/networks/{star_net}/templates/star").json()
    assert {l["source"] for l in star["links"]} == {"node_001"}  # every link starts at the hub


def test_ring_is_a_cycle(client, network_id):
    client.post(f"/api/networks/{network_id}/templates/ring")
    graph = graph_manager.get_graph(network_id)
    assert all(degree == 2 for _, degree in graph.degree())


def test_custom_node_count_and_link_properties(client, network_id):
    response = client.post(
        f"/api/networks/{network_id}/templates/mesh", json={"node_count": 5, "bandwidth": 1000, "latency": 2}
    )
    body = response.json()
    assert body["summary"]["links"] == 10  # 5 * 4 / 2
    assert {(l["bandwidth"], l["latency"]) for l in body["links"]} == {(1000, 2)}


@pytest.mark.parametrize(("template", "count"), [("ring", 2), ("mesh", 13), ("linear", 1), ("star", 2)])
def test_out_of_range_node_count(client, network_id, template, count):
    response = client.post(f"/api/networks/{network_id}/templates/{template}", json={"node_count": count})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_node_count"
    assert client.get(f"/api/networks/{network_id}/nodes").json() == []  # nothing half-created


def test_template_requires_empty_network(client, network_id):
    make_node(client, network_id, "Router-A")
    response = client.post(f"/api/networks/{network_id}/templates/ring")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "network_not_empty"


def test_template_on_missing_network_and_unknown_template(client, network_id):
    assert client.post("/api/networks/net_999/templates/ring").status_code == 404
    assert client.post(f"/api/networks/{network_id}/templates/torus").status_code == 400
