import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_analytics_api_empty():
    network_id = "net_test_analytics_001"
    
    # Summary
    res = client.get(f"/api/networks/{network_id}/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["experiments_analyzed"] == 0
    assert data["successful_recoveries"] == 0
    
    # Failures
    res = client.get(f"/api/networks/{network_id}/analytics/failures")
    assert res.status_code == 200
    assert len(res.json()) == 0

def test_analytics_compare_empty():
    res = client.post("/api/analytics/compare", json={"experiment_ids": ["exp_001", "exp_002"]})
    assert res.status_code == 200
    data = res.json()
    assert len(data["experiments"]) == 0
