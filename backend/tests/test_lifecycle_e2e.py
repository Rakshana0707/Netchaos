"""Full lifecycle through the public API: baseline -> chaos -> detection -> recovery -> post-recovery -> analytics."""
import pytest
from tests.conftest import build_canonical, run_sim


def lifecycle(client, topo, fail: str, recover: bool = True):
    """Run one experiment failing `fail` ('link:BD' or 'node:B'/'node:D'). Returns (experiment_id, ids, post)."""
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/failures/baseline")
    exp = client.post(f"/api/networks/{nid}/experiments", json={"name": f"fail {fail}", "description": "t"}).json()["id"]
    base = run_sim(client, nid, n["A"], n["D"])
    kind, target = fail.split(":")
    if kind == "link":
        chaos = client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"][target]})
    else:
        chaos = client.post(f"/api/networks/{nid}/chaos/router-failure", json={"node_id": n[target]})
    assert chaos.status_code == 201, chaos.json()
    chaos_id = chaos.json()["experiment_id"]
    chaos_sim = run_sim(client, nid, n["A"], n["D"])
    det = client.post(f"/api/networks/{nid}/failures/detect").json()
    ids = {"baseline_simulation_id": base["id"], "chaos_simulation_id": chaos_sim["id"],
           "chaos_experiment_ids": [chaos_id], "detection_id": det["id"]}
    post = None
    if recover:
        rec = client.post(f"/api/networks/{nid}/recovery", json={"simulation_id": base["id"], "strategy": "shortest_hop"}).json()
        ids["recovery_id"] = rec["recovery_id"]
        if rec["status"] == "RECOVERED":
            post = run_sim(client, nid, n["A"], n["D"], recovery_id=rec["recovery_id"])
            ids["post_recovery_simulation_id"] = post["id"]
    client.post(f"/api/networks/{nid}/chaos/{chaos_id}/revert")
    r = client.post(f"/api/experiments/{exp}/phases", json=ids)
    assert r.status_code == 200, r.json()
    client.post(f"/api/experiments/{exp}/complete")
    return exp, ids, post


def test_recovered_lifecycle(client):
    topo = build_canonical(client)
    exp, ids, post = lifecycle(client, topo, "link:BD")
    nid = topo["network_id"]
    assert post["route"] == [topo["nodes"]["A"], topo["nodes"]["C"], topo["nodes"]["D"]] or len(post["route"]) == 3
    assert post["path_latency_ms"] == 40.0

    a = client.get(f"/api/experiments/{exp}").json()["metrics"]
    assert a["recovery_status"] == "recovered"
    assert a["connectivity_during_chaos"] == 0.0
    assert a["connectivity_preservation"] == 100.0
    assert a["phases"]["baseline"]["latency_ms"] == 20.0
    assert a["phases"]["post_recovery"]["latency_ms"] == 40.0
    assert a["phases"]["chaos"]["packet_loss_percent"] == 100.0
    assert a["post_recovery_latency_degradation_percent"] == 100.0
    assert a["recovery_time_seconds"] is not None and a["recovery_time_seconds"] >= 0
    assert 0 < a["impact_score"] <= 1

    # chaos was reverted: topology is whole again
    links = client.get(f"/api/networks/{nid}/topology").json()["links"]
    assert all(link["status"] == "active" for link in links)

    summary = client.get(f"/api/networks/{nid}/analytics/summary").json()
    assert summary["experiments_analyzed"] == 1
    assert summary["successful_recoveries"] == 1
    assert summary["resilience_score"] == 100.0

    report = client.get(f"/api/experiments/{exp}/report").json()
    assert report["route_analysis"]["route_changed"] is True
    assert "benchmark" in report["disclaimer"]


def test_unrecoverable_lifecycle(client):
    topo = build_canonical(client)
    exp, ids, post = lifecycle(client, topo, "node:D")
    assert post is None
    a = client.get(f"/api/experiments/{exp}").json()["metrics"]
    assert a["recovery_status"] == "unrecoverable"
    assert a["recoverable"] is False
    assert a["connectivity_preservation"] == 0.0
    assert a["recovery_effectiveness_percent"] == 0.0
    assert a["impact_score"] > 0.8
    summary = client.get(f"/api/networks/{topo['network_id']}/analytics/summary").json()
    assert summary["failed_recoveries"] == 1
    assert summary["resilience_score"] == 0.0
    ranking = client.get(f"/api/networks/{topo['network_id']}/analytics/failures").json()
    assert ranking[0]["severity"] == "critical"


def test_mixed_summary_and_ranking(client):
    topo = build_canonical(client)
    ok, _, _ = lifecycle(client, topo, "link:BD")
    bad, _, _ = lifecycle(client, topo, "node:D")
    nid = topo["network_id"]
    summary = client.get(f"/api/networks/{nid}/analytics/summary").json()
    assert summary["experiments_analyzed"] == 2
    assert summary["successful_recoveries"] == 1 and summary["failed_recoveries"] == 1
    assert summary["resilience_score"] == 50.0
    ranking = client.get(f"/api/networks/{nid}/analytics/failures").json()
    assert [r["experiment_id"] for r in ranking] == [bad, ok]
    cmp = client.post("/api/analytics/compare", json={"experiment_ids": [ok, bad, "exp_nope"]}).json()
    assert len(cmp["experiments"]) == 2


def test_non_critical_chaos_needs_no_recovery(client):
    topo = build_canonical(client)
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/failures/baseline")
    exp = client.post(f"/api/networks/{nid}/experiments", json={"name": "lat", "description": "t"}).json()["id"]
    base = run_sim(client, nid, n["A"], n["D"])
    chaos = client.post(f"/api/networks/{nid}/chaos/latency", json={"link_id": topo["links"]["AB"], "latency": 100})
    assert chaos.status_code == 201, chaos.json()
    cid = chaos.json()["experiment_id"]
    sim = run_sim(client, nid, n["A"], n["D"])
    client.post(f"/api/networks/{nid}/chaos/{cid}/revert")
    client.post(f"/api/experiments/{exp}/phases", json={
        "baseline_simulation_id": base["id"], "chaos_simulation_id": sim["id"], "chaos_experiment_ids": [cid]})
    client.post(f"/api/experiments/{exp}/complete")
    m = client.get(f"/api/experiments/{exp}").json()["metrics"]
    assert m["recovery_status"] == "not_required"
    assert m["connectivity_preservation"] == 100.0
    assert m["latency_degradation_percent"] is not None and m["latency_degradation_percent"] > 0


def test_phases_validation(client):
    topo = build_canonical(client)
    nid = topo["network_id"]
    exp = client.post(f"/api/networks/{nid}/experiments", json={"name": "x", "description": "t"}).json()["id"]
    r = client.post(f"/api/experiments/{exp}/phases", json={"baseline_simulation_id": "sim_999"})
    assert r.status_code == 404
    assert client.post("/api/experiments/exp_zzz/phases", json={}).status_code == 404


def test_incomplete_experiment_reports_missing_not_zeros(client):
    topo = build_canonical(client)
    nid = topo["network_id"]
    exp = client.post(f"/api/networks/{nid}/experiments", json={"name": "empty", "description": "t"}).json()["id"]
    client.post(f"/api/experiments/{exp}/complete")
    a = client.get(f"/api/experiments/{exp}/report").json()
    assert a["data_complete"] is False and a["resilience_score"] is None
    assert client.get(f"/api/networks/{nid}/analytics/summary").json()["experiments_analyzed"] == 0
