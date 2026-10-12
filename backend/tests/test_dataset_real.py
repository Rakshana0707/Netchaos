"""Dataset records must come from real linked lifecycle data."""
from tests.conftest import build_canonical
from tests.test_lifecycle_e2e import lifecycle


def test_dataset_from_linked_experiments(client):
    topo = build_canonical(client)
    ok, _, _ = lifecycle(client, topo, "link:BD")
    bad, _, _ = lifecycle(client, topo, "node:D")
    res = client.post("/api/datasets", json={"name": "real", "version": "1.0"})
    assert res.status_code == 200, res.text
    ds = client.get(f"/api/datasets/{res.json()['dataset_id']}").json()
    recs = {r["experiment_id"]: r for r in ds["records"]}
    assert set(recs) == {ok, bad}
    r = recs[ok]
    assert r["recovery_outcome"] == "RECOVERED" and r["chaos_type"] == "link_failure"
    assert r["baseline_latency"] == 20.0 and r["recovered_latency"] == 40.0
    assert r["packet_count"] == 100 and r["failure_detected"] is True
    assert r["resilience_score"] == 100.0
    assert recs[bad]["recovery_outcome"] == "UNRECOVERABLE"
    assert recs[bad]["recovered_latency"] is None
    stats = client.get(f"/api/datasets/{res.json()['dataset_id']}/statistics")
    assert stats.status_code == 200 and stats.json()["total_records"] == 2
