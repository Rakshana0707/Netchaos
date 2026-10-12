import pytest

from tests.conftest import link_payload, make_node


@pytest.fixture()
def two_nodes(client, network_id):
    return make_node(client, network_id, "Router-A"), make_node(client, network_id, "Router-B")


def test_create_link(client, network_id, two_nodes):
    a, b = two_nodes
    response = client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b))
    assert response.status_code == 201
    body = response.json()
    assert body["link_id"] == "link_001"
    assert (body["source"], body["destination"]) == (a, b)
    assert body["bandwidth"] == 100 and body["latency"] == 10
    assert body["packet_loss"] == 0
    assert body["status"] == "active"


def test_get_list_delete_link(client, network_id, two_nodes):
    a, b = two_nodes
    link_id = client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b)).json()["link_id"]
    assert client.get(f"/api/networks/{network_id}/links/{link_id}").status_code == 200
    assert len(client.get(f"/api/networks/{network_id}/links").json()) == 1
    assert client.delete(f"/api/networks/{network_id}/links/{link_id}").status_code == 204
    assert client.get(f"/api/networks/{network_id}/links/{link_id}").status_code == 404
    assert client.delete(f"/api/networks/{network_id}/links/{link_id}").status_code == 404


def test_invalid_source(client, network_id, two_nodes):
    response = client.post(f"/api/networks/{network_id}/links", json=link_payload("node_999", two_nodes[1]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "node_not_found"


def test_invalid_destination(client, network_id, two_nodes):
    response = client.post(f"/api/networks/{network_id}/links", json=link_payload(two_nodes[0], "node_999"))
    assert response.status_code == 404


def test_node_from_another_network_is_rejected(client, network_id, two_nodes):
    other = client.post("/api/networks", json={"name": "Other"}).json()["network_id"]
    for name in ("X", "Y", "Z"):
        foreign = make_node(client, other, name)  # ends as node_003, which does not exist in network_id
    response = client.post(f"/api/networks/{network_id}/links", json=link_payload(two_nodes[0], foreign))
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"bandwidth": 0}, "invalid_bandwidth"),
        ({"bandwidth": -5}, "invalid_bandwidth"),
        ({"latency": -1}, "invalid_latency"),
        ({"packet_loss": -0.1}, "invalid_packet_loss"),
        ({"packet_loss": 100.1}, "invalid_packet_loss"),
    ],
)
def test_invalid_link_values(client, network_id, two_nodes, overrides, code):
    payload = link_payload(*two_nodes, **overrides)
    response = client.post(f"/api/networks/{network_id}/links", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_boundary_values_are_accepted(client, network_id, two_nodes):
    payload = link_payload(*two_nodes, latency=0, packet_loss=100)
    assert client.post(f"/api/networks/{network_id}/links", json=payload).status_code == 201


def test_duplicate_link_in_either_direction(client, network_id, two_nodes):
    a, b = two_nodes
    assert client.post(f"/api/networks/{network_id}/links", json=link_payload(a, b)).status_code == 201
    for source, destination in ((a, b), (b, a)):
        response = client.post(f"/api/networks/{network_id}/links", json=link_payload(source, destination))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "duplicate_link"


def test_self_link_rejected(client, network_id, two_nodes):
    response = client.post(f"/api/networks/{network_id}/links", json=link_payload(two_nodes[0], two_nodes[0]))
    assert response.status_code == 400


def test_link_in_nonexistent_network(client):
    response = client.post("/api/networks/net_999/links", json=link_payload("node_001", "node_002"))
    assert response.status_code == 404
