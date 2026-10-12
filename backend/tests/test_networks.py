def test_create_network(client):
    response = client.post("/api/networks", json={"name": "Campus Network"})
    assert response.status_code == 201
    body = response.json()
    assert body["network_id"] == "net_001"
    assert body["name"] == "Campus Network"


def test_network_ids_increment(client):
    ids = [client.post("/api/networks", json={"name": f"N{i}"}).json()["network_id"] for i in range(3)]
    assert ids == ["net_001", "net_002", "net_003"]


def test_retrieve_network(client, network_id):
    response = client.get(f"/api/networks/{network_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Campus Network"
    assert len(client.get("/api/networks").json()) == 1


def test_nonexistent_network(client):
    response = client.get("/api/networks/net_999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "network_not_found"


def test_blank_network_name_rejected(client):
    response = client.post("/api/networks", json={"name": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_name"
