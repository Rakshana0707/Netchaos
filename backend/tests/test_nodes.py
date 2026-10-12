import pytest

from tests.conftest import make_node


@pytest.mark.parametrize("node_type", ["router", "host", "server", "client"])
def test_add_each_node_type(client, network_id, node_type):
    response = client.post(f"/api/networks/{network_id}/nodes", json={"name": "N1", "type": node_type})
    assert response.status_code == 201
    body = response.json()
    assert body["node_id"] == "node_001"
    assert body["network_id"] == network_id
    assert body["type"] == node_type
    assert body["status"] == "active"
    assert body["created_at"]


def test_invalid_node_type(client, network_id):
    response = client.post(f"/api/networks/{network_id}/nodes", json={"name": "X", "type": "toaster"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_node_type"


def test_duplicate_node_name(client, network_id):
    make_node(client, network_id, "Router-A")
    response = client.post(f"/api/networks/{network_id}/nodes", json={"name": "Router-A", "type": "router"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_node"


def test_same_name_allowed_in_different_networks(client, network_id):
    other = client.post("/api/networks", json={"name": "Other"}).json()["network_id"]
    make_node(client, network_id, "Router-A")
    make_node(client, other, "Router-A")


def test_add_node_to_nonexistent_network(client):
    response = client.post("/api/networks/net_999/nodes", json={"name": "R", "type": "router"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "network_not_found"


def test_get_and_list_nodes(client, network_id):
    node_id = make_node(client, network_id, "Router-A")
    assert client.get(f"/api/networks/{network_id}/nodes/{node_id}").json()["name"] == "Router-A"
    assert len(client.get(f"/api/networks/{network_id}/nodes").json()) == 1
    missing = client.get(f"/api/networks/{network_id}/nodes/node_999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "node_not_found"


def test_node_ids_are_not_reused_after_delete(client, network_id):
    first = make_node(client, network_id, "A")
    assert client.delete(f"/api/networks/{network_id}/nodes/{first}").status_code == 204
    assert make_node(client, network_id, "B") == "node_002"


def test_delete_missing_node(client, network_id):
    assert client.delete(f"/api/networks/{network_id}/nodes/node_999").status_code == 404
