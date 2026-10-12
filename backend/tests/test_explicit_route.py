"""Post-recovery traffic must use exactly the recovered route; the simulator never reroutes on its own."""
from tests.conftest import build_canonical, run_sim


def _recover(client, topo):
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/failures/baseline")
    base = run_sim(client, nid, n["A"], n["D"])
    chaos = client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["BD"]}).json()
    client.post(f"/api/networks/{nid}/failures/detect")
    rec = client.post(f"/api/networks/{nid}/recovery", json={"simulation_id": base["id"], "strategy": "shortest_hop"}).json()
    return base, chaos["experiment_id"], rec


def test_post_recovery_uses_recovered_route(client):
    topo = build_canonical(client)
    base, _, rec = _recover(client, topo)
    n = topo["nodes"]
    post = run_sim(client, topo["network_id"], n["A"], n["D"], recovery_id=rec["recovery_id"])
    assert post["route"] == rec["recovered_route"]
    assert post["status"] == "completed"
    # the original baseline record is untouched
    again = client.get(f"/api/networks/{topo['network_id']}/traffic/simulations/{base['id']}").json()
    assert again["path_latency_ms"] == 20.0


def test_plain_traffic_never_reroutes_over_failed_link(client):
    topo = build_canonical(client)
    _, _, _ = _recover(client, topo)
    n = topo["nodes"]
    # without recovery_id, shortest path A-C-D still exists, so plain traffic may use it; but A->B->D must not
    sim = run_sim(client, topo["network_id"], n["A"], n["D"])
    assert topo["nodes"]["B"] not in (sim.get("route") or [])


def test_recovery_id_validation(client):
    topo = build_canonical(client)
    n = topo["network_id"], topo["nodes"]
    r = client.post(f"/api/networks/{n[0]}/traffic/simulations", json={
        "source": n[1]["A"], "destination": n[1]["D"], "packet_count": 10, "packet_size": 100, "recovery_id": "rec_999_999"})
    assert r.status_code in (400, 404)


def test_recovery_fails_route_when_recovered_link_later_dies(client):
    topo = build_canonical(client)
    _, _, rec = _recover(client, topo)
    nid, n = topo["network_id"], topo["nodes"]
    client.post(f"/api/networks/{nid}/chaos/link-failure", json={"link_id": topo["links"]["CD"]})
    post = run_sim(client, nid, n["A"], n["D"], recovery_id=rec["recovery_id"])
    assert post["status"] == "failed"
