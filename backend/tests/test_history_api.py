import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
import time

from app.main import app
from app.database.database import get_mongo_db
from app.graph import graph_manager

@pytest.fixture(scope="session")
def mongo_client():
    client = MongoClient("mongodb://localhost:27017/")
    yield client
    client.drop_database("netchaos_test_hist")
    client.close()

@pytest.fixture()
def client(mongo_client):
    db = mongo_client["netchaos_test_hist"]
    def override_get_mongo_db():
        yield db

    app.dependency_overrides[get_mongo_db] = override_get_mongo_db
    graph_manager.clear()
    
    for name in db.list_collection_names():
        db[name].delete_many({})
        
    yield TestClient(app)
    app.dependency_overrides.clear()
    graph_manager.clear()

def test_history_workflow(client):
    db = next(app.dependency_overrides[get_mongo_db]())
    db.networks.insert_one({"id": "net_h01", "name": "History Net"})
    
    # 1. Create experiment
    res = client.post("/api/networks/net_h01/experiments", json={"name": "Latency Test", "description": "Verify Module 7"})
    assert res.status_code == 200
    exp_id = res.json()["id"]
    
    from datetime import datetime, timezone, timedelta
    
    # 2. Mock Snapshots and Chaos
    now = datetime.now(timezone.utc).replace(microsecond=0)
    db.monitoring_snapshots.insert_many([
        {"id": "snap_1", "network_id": "net_h01", "timestamp": now + timedelta(seconds=1), "health_status": "HEALTHY", "nodes": {"failed":0}, "links": {"failed":0}, "traffic": {"average_latency": 10, "packet_loss_percentage": 0, "throughput": 100}, "connectivity": {"partitions":1, "traffic_availability": 100}},
        {"id": "snap_2", "network_id": "net_h01", "timestamp": now + timedelta(seconds=2), "health_status": "DEGRADED", "nodes": {"failed":0}, "links": {"failed":0}, "traffic": {"average_latency": 150, "packet_loss_percentage": 5, "throughput": 20}, "connectivity": {"partitions":1, "traffic_availability": 100}},
        {"id": "snap_3", "network_id": "net_h01", "timestamp": now + timedelta(seconds=3), "health_status": "HEALTHY", "nodes": {"failed":0}, "links": {"failed":0}, "traffic": {"average_latency": 15, "packet_loss_percentage": 0, "throughput": 90}, "connectivity": {"partitions":1, "traffic_availability": 100}}
    ])
    
    db.chaos_experiments.insert_one({
        "id": "chaos_1", "network_id": "net_h01", "created_at": now + timedelta(seconds=1.5), "chaos_type": "latency_spike"
    })
    
    # Expand experiment time bounds
    db.experiments.update_one({"id": exp_id}, {"$set": {"started_at": now - timedelta(seconds=10)}})
    
    # 3. Complete experiment
    client.post(f"/api/experiments/{exp_id}/complete")
    db.experiments.update_one({"id": exp_id}, {"$set": {"ended_at": now + timedelta(seconds=10)}})

    
    # 4. Fetch details
    res = client.get(f"/api/experiments/{exp_id}")
    assert res.status_code == 200
    data = res.json()
    
    assert data["experiment"]["status"] == "COMPLETED"
    assert len(data["timeline"]) == 6 # create + 3 snaps + 1 chaos + complete
    
    perf = data["performance_analysis"]
    assert perf["latency"]["degradation_absolute"] == 140 # 150 - 10
    
    # 5. Compare API
    res = client.post("/api/experiments/compare", json=[exp_id])
    assert res.status_code == 200
    assert len(res.json()) == 1
