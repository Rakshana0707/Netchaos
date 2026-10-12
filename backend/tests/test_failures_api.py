import pytest

def test_create_baseline(client, network_id):
    resp_n1 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "A", "type": "router"})
    resp_n2 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "B", "type": "router"})
    node1_id = resp_n1.json()["node_id"]
    node2_id = resp_n2.json()["node_id"]
    
    resp_l = client.post(f"/api/networks/{network_id}/links", json={"source": node1_id, "destination": node2_id, "bandwidth": 100, "latency": 10})
    
    response = client.post(f"/api/networks/{network_id}/failures/baseline")
    assert response.status_code == 201
    data = response.json()
    assert data["network_id"] == network_id
    assert data["is_active"] is True
    assert len(data["nodes"]) == 2
    assert len(data["links"]) == 1

def test_detect_failures_healthy(client, network_id):
    resp_n1 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "A", "type": "router"})
    resp_n2 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "B", "type": "router"})
    node1_id = resp_n1.json()["node_id"]
    node2_id = resp_n2.json()["node_id"]
    
    client.post(f"/api/networks/{network_id}/links", json={"source": node1_id, "destination": node2_id, "bandwidth": 100, "latency": 10})
    
    client.post(f"/api/networks/{network_id}/failures/baseline")
    
    response = client.post(f"/api/networks/{network_id}/failures/detect")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "healthy"
    assert data["failed_nodes"] == 0
    assert data["failed_links"] == 0
    assert data["connected_components"] == 1

def test_detect_node_failure(client, network_id):
    resp_n1 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "A", "type": "router"})
    resp_n2 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "B", "type": "router"})
    node1_id = resp_n1.json()["node_id"]
    node2_id = resp_n2.json()["node_id"]
    
    client.post(f"/api/networks/{network_id}/links", json={"source": node1_id, "destination": node2_id, "bandwidth": 100, "latency": 10})
    
    client.post(f"/api/networks/{network_id}/failures/baseline")
    
    # Inject failure
    client.post(f"/api/networks/{network_id}/chaos/router-failure", json={"node_id": node2_id})
    
    response = client.post(f"/api/networks/{network_id}/failures/detect")
    data = response.json()
    assert data["overall_status"] == "critical"
    assert data["failed_nodes"] == 1
    
    failures = data["failures"]
    assert any(f["failure_type"] == "node_failure" and f["target_id"] == node2_id for f in failures)
    
def test_detect_partition(client, network_id):
    resp_n1 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "A", "type": "router"})
    resp_n2 = client.post(f"/api/networks/{network_id}/nodes", json={"name": "B", "type": "router"})
    node1_id = resp_n1.json()["node_id"]
    node2_id = resp_n2.json()["node_id"]
    
    resp_l = client.post(f"/api/networks/{network_id}/links", json={"source": node1_id, "destination": node2_id, "bandwidth": 100, "latency": 10})
    link_id = resp_l.json()["link_id"]
    
    client.post(f"/api/networks/{network_id}/failures/baseline")
    
    # Fail the link
    client.post(f"/api/networks/{network_id}/chaos/link-failure", json={"link_id": link_id})
    
    response = client.post(f"/api/networks/{network_id}/failures/detect")
    data = response.json()
    assert data["connected_components"] == 2
    assert any(f["failure_type"] == "network_partition" for f in data["failures"])
