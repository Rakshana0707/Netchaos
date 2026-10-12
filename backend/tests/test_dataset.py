import pytest
import time
import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.database.database import get_mongo_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    from app.database.database import get_mongo_db
    from app.graph import graph_manager
    db = next(get_mongo_db())
    db.networks.delete_many({})
    db.nodes.delete_many({})
    db.links.delete_many({})
    db.traffic_simulations.delete_many({})
    db.chaos_experiments.delete_many({})
    db.recovery_events.delete_many({})
    db.experiments.delete_many({})
    db.experiment_plans.delete_many({})
    db.datasets.delete_many({})
    db.dataset_records.delete_many({})
    graph_manager.clear()
    
    yield
    
    db.networks.delete_many({})
    db.experiment_plans.delete_many({})
    db.datasets.delete_many({})
    db.dataset_records.delete_many({})
    db.experiments.delete_many({})
    graph_manager.clear()

def test_dataset_generation():
    # Create simple experiments
    db = next(get_mongo_db())
    # Faking an experiment in DB
    db.experiments.insert_one({
        "id": "exp_001",
        "network_id": "net_001",
        "status": "COMPLETED",
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
        "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
        "baseline_state": {},
        "chaos_events": [{"type": "link_failure", "target": "link_002"}],
        "failure_events": [{}],
        "recovery_events": [{"status": "SUCCESS"}],
        "simulations": ["sim_1", "sim_2", "sim_3"]
    })
    
    # Generate Dataset
    req = {
        "name": "Test Dataset",
        "description": "A dataset for testing",
        "version": "1.0",
        "filters": {}
    }
    res = client.post("/api/datasets", json=req)
    if res.status_code != 200:
        print(f"FAILED: {res.status_code}, {res.text}")
    assert res.status_code == 200
    manifest = res.json()
    assert manifest["name"] == "Test Dataset"
    assert manifest["record_count"] == 1
    ds_id = manifest["dataset_id"]
    
    # Get Dataset
    res2 = client.get(f"/api/datasets/{ds_id}")
    assert res2.status_code == 200
    ds = res2.json()
    assert len(ds["records"]) == 1
    rec = ds["records"][0]
    
    assert rec["experiment_id"] == "exp_001"
    assert rec["chaos_type"] == "link_failure"
    assert rec["recovery_outcome"] == "RECOVERED"
    assert rec["failure_detected"] == True

    # Get stats
    res3 = client.get(f"/api/datasets/{ds_id}/statistics")
    assert res3.status_code == 200
    stats = res3.json()
    assert stats["total_records"] == 1
    assert stats["recovery_distribution"]["RECOVERED"] == 1

def test_dataset_filters():
    db = next(get_mongo_db())
    db.experiments.insert_one({
        "id": "exp_001",
        "network_id": "net_001",
        "status": "COMPLETED",
        "chaos_events": [{"type": "link_failure"}],
        "recovery_events": [{"status": "SUCCESS"}]
    })
    db.experiments.insert_one({
        "id": "exp_002",
        "network_id": "net_001",
        "status": "COMPLETED",
        "chaos_events": [{"type": "packet_loss"}],
        "recovery_events": [{"status": "FAILED"}]
    })
    
    # Filter by chaos_type
    req = {
        "name": "Filtered Dataset",
        "version": "1.0",
        "filters": {"failure_types": ["link_failure"]}
    }
    res = client.post("/api/datasets", json=req)
    manifest = res.json()
    assert manifest["record_count"] == 1
    
    req2 = {
        "name": "Filtered Dataset 2",
        "version": "1.0",
        "filters": {"recovery_outcomes": ["UNRECOVERABLE"]}
    }
    res2 = client.post("/api/datasets", json=req2)
    manifest2 = res2.json()
    assert manifest2["record_count"] == 1
    
def test_dataset_export():
    db = next(get_mongo_db())
    db.experiments.insert_one({
        "id": "exp_001",
        "network_id": "net_001",
        "status": "COMPLETED",
        "chaos_events": [{"type": "link_failure"}]
    })
    
    res = client.post("/api/datasets", json={"name": "Export Test", "version": "1.0"})
    ds_id = res.json()["dataset_id"]
    
    res_csv = client.get(f"/api/datasets/{ds_id}/export/csv")
    assert res_csv.status_code == 200
    assert "experiment_id" in res_csv.text
    
    res_json = client.get(f"/api/datasets/{ds_id}/export/json")
    assert res_json.status_code == 200
    assert "exp_001" in res_json.text
