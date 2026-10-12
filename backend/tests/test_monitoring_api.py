import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import app
from app.database.database import get_mongo_db
from app.graph import graph_manager

@pytest.fixture(scope="session")
def mongo_client():
    client = MongoClient("mongodb://localhost:27017/")
    yield client
    client.drop_database("netchaos_test")
    client.close()

@pytest.fixture()
def client(mongo_client):
    db = mongo_client["netchaos_test"]
    def override_get_mongo_db():
        yield db

    app.dependency_overrides[get_mongo_db] = override_get_mongo_db
    graph_manager.clear()
    
    for name in db.list_collection_names():
        db[name].delete_many({})
        
    yield TestClient(app)
    app.dependency_overrides.clear()
    graph_manager.clear()

def test_monitoring_endpoints(client):
    db = next(app.dependency_overrides[get_mongo_db]())
    
    db.networks.insert_one({"id": "net_001", "name": "Test"})
    db.nodes.insert_one({"id": "node_a", "network_id": "net_001", "name": "A", "status": "active"})
    db.nodes.insert_one({"id": "node_b", "network_id": "net_001", "name": "B", "status": "active"})
    db.links.insert_one({"id": "link_1", "network_id": "net_001", "source_node_id": "node_a", "destination_node_id": "node_b", "status": "active", "bandwidth": 100, "latency": 10, "packet_loss": 0})
    
    # Baseline
    resp = client.post("/api/networks/net_001/monitoring/snapshot")
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["health_status"] == "HEALTHY"
    
    # Links
    resp = client.get("/api/networks/net_001/monitoring/links")
    assert len(resp.json()) == 1
    
    # Traffic
    resp = client.get("/api/networks/net_001/monitoring/traffic")
    assert resp.json()["active_flows"] == 0

    # Inject failure directly
    db.links.update_one({"id": "link_1"}, {"$set": {"status": "failed"}})
    resp = client.post("/api/networks/net_001/monitoring/snapshot")
    snap = resp.json()
    assert snap["health_status"] == "CRITICAL" # Partition count is now > 1, failed link > 0
    
    # History
    resp = client.get("/api/networks/net_001/monitoring/history")
    assert len(resp.json()) == 2
