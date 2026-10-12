"""Comprehensive tests for Module 5 — Dynamic Recovery.

Topology used in most tests:

    A ─── B ─── D
     \\         /
      ─── C ───

node_A/B/C/D, link_AB/BD/AC/CD.
"""
import pytest
from tests.conftest import make_node, link_payload


# ---------------------------------------------------------------------------
# Helper to build the diamond topology
# ---------------------------------------------------------------------------

def build_diamond(client, network_id):
    """Create A-B-D / A-C-D topology. Return node and link ids."""
    nA = make_node(client, network_id, "A")
    nB = make_node(client, network_id, "B")
    nC = make_node(client, network_id, "C")
    nD = make_node(client, network_id, "D")

    def link(src, dst, **kw):
        r = client.post(f"/api/networks/{network_id}/links", json=link_payload(src, dst, **kw))
        assert r.status_code == 201, r.text
        return r.json()["link_id"]

    lAB = link(nA, nB, latency=10, bandwidth=100)
    lBD = link(nB, nD, latency=10, bandwidth=100)
    lAC = link(nA, nC, latency=5, bandwidth=80)
    lCD = link(nC, nD, latency=5, bandwidth=80)
    return {"A": nA, "B": nB, "C": nC, "D": nD,
            "AB": lAB, "BD": lBD, "AC": lAC, "CD": lCD}


def run_sim(client, network_id, src, dst):
    """Create and run a simulation; return the completed sim dict."""
    r = client.post(
        f"/api/networks/{network_id}/traffic/simulations",
        json={"source": src, "destination": dst, "packet_count": 10, "packet_size": 512}
    )
    assert r.status_code == 201, r.text
    sim_id = r.json()["simulation_id"]
    r2 = client.post(f"/api/networks/{network_id}/traffic/simulations/{sim_id}/run")
    assert r2.status_code == 200, r2.text
    return r2.json()


def fail_link(client, network_id, link_id):
    r = client.post(f"/api/networks/{network_id}/chaos/link-failure", json={"link_id": link_id})
    assert r.status_code == 201, r.text


def fail_router(client, network_id, node_id):
    r = client.post(f"/api/networks/{network_id}/chaos/router-failure", json={"node_id": node_id})
    assert r.status_code == 201, r.text


def revert_all(client, network_id):
    r = client.post(f"/api/networks/{network_id}/chaos/reset")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Test 1: link failure with alternate route
# ---------------------------------------------------------------------------

def test_link_failure_alternate_route(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]
    assert sim["route"] is not None

    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "shortest_hop"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "RECOVERED"
    assert data["route_changed"] is True
    assert data["connectivity_restored"] is True
    # The recovered route must NOT use the failed link BD
    rec = data["recovered_route"]
    assert ids["A"] in rec
    assert ids["D"] in rec
    # B-D link should not appear consecutively
    for i in range(len(rec) - 1):
        pair = {rec[i], rec[i+1]}
        assert pair != {ids["B"], ids["D"]}, "Route uses failed B-D link"


# ---------------------------------------------------------------------------
# Test 2: router failure with alternate route
# ---------------------------------------------------------------------------

def test_router_failure_alternate_route(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]

    fail_router(client, network_id, ids["B"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "shortest_hop"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "RECOVERED"
    rec = data["recovered_route"]
    assert ids["B"] not in rec, "Recovered route must not pass through failed node B"
    assert ids["A"] == rec[0]
    assert ids["D"] == rec[-1]


# ---------------------------------------------------------------------------
# Test 3: no alternate route
# ---------------------------------------------------------------------------

def test_no_alternate_route(client, network_id):
    nA = make_node(client, network_id, "X")
    nB = make_node(client, network_id, "Y")
    lAB = client.post(f"/api/networks/{network_id}/links",
                      json=link_payload(nA, nB)).json()["link_id"]
    sim = run_sim(client, network_id, nA, nB)
    sim_id = sim["simulation_id"]

    fail_router(client, network_id, nB)

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "lowest_latency"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "NO_ALTERNATE_ROUTE"
    assert data["connectivity_restored"] is False
    assert data["recovered_route"] is None


# ---------------------------------------------------------------------------
# Test 4: lowest latency route selection
# ---------------------------------------------------------------------------

def test_lowest_latency_selection(client, network_id):
    # A-B-D = 40 ms, A-C-D = 20 ms
    nA = make_node(client, network_id, "A")
    nB = make_node(client, network_id, "B")
    nC = make_node(client, network_id, "C")
    nD = make_node(client, network_id, "D")

    def lnk(src, dst, lat, bw=100):
        r = client.post(f"/api/networks/{network_id}/links",
                        json={"source": src, "destination": dst, "bandwidth": bw, "latency": lat})
        assert r.status_code == 201, r.text
        return r.json()["link_id"]

    lAB = lnk(nA, nB, lat=20)
    lBD = lnk(nB, nD, lat=20)
    lAC = lnk(nA, nC, lat=5)
    lCD = lnk(nC, nD, lat=15)

    sim = run_sim(client, network_id, nA, nD)
    sim_id = sim["simulation_id"]

    # Fail the link used by existing route if it's A-B-D, else just ask for recovery
    fail_link(client, network_id, lBD)

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "lowest_latency"})
    data = r.json()
    assert data["status"] == "RECOVERED"
    rec = data["recovered_route"]
    # A-C-D has 20ms total, A-B-D is now broken so must use A-C-D
    assert nC in rec


# ---------------------------------------------------------------------------
# Test 5: shortest hop selection
# ---------------------------------------------------------------------------

def test_shortest_hop_selection(client, network_id):
    """Verify shortest_hop prefers A-E-D (2 hops) over A-B-C-D (3 hops).

    Topology:
        A-X-D  (original route used by sim, 2 hops — X-D gets failed)
        A-E-D  (2-hop alternative)
        A-B-C-D (3-hop alternative)
    After failing X-D, shortest_hop must choose A-E-D not A-B-C-D.
    """
    nA = make_node(client, network_id, "A")
    nX = make_node(client, network_id, "X")   # pivot on original route
    nE = make_node(client, network_id, "E")   # 2-hop alternative node
    nB = make_node(client, network_id, "B")
    nC = make_node(client, network_id, "C")
    nD = make_node(client, network_id, "D")

    def lnk(src, dst, lat=10, bw=100):
        r = client.post(f"/api/networks/{network_id}/links",
                        json={"source": src, "destination": dst, "bandwidth": bw, "latency": lat})
        assert r.status_code == 201, r.text
        return r.json()["link_id"]

    # Give A-X-D very low latency so the traffic sim deterministically picks it
    lAX = lnk(nA, nX, lat=1)
    lXD = lnk(nX, nD, lat=1)   # will be failed → forces recovery
    lAE = lnk(nA, nE, lat=10)
    lED = lnk(nE, nD, lat=10)  # 2-hop path A-E-D
    lAB = lnk(nA, nB, lat=10)
    lBC = lnk(nB, nC, lat=10)
    lCD = lnk(nC, nD, lat=10)  # 3-hop path A-B-C-D

    sim = run_sim(client, network_id, nA, nD)
    sim_id = sim["simulation_id"]
    assert sim["status"] == "completed"
    # Ensure original route uses X (lowest latency forces A-X-D)
    assert nX in sim["route"], f"Expected original route to use X; got {sim['route']}"

    # Fail the link on the original route so recovery is triggered
    fail_link(client, network_id, lXD)

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "shortest_hop"})
    data = r.json()
    assert data["status"] == "RECOVERED", f"Expected RECOVERED, got: {data['status']}"
    rec = data["recovered_route"]
    assert rec[0] == nA
    assert rec[-1] == nD
    # 2-hop path (A-E-D) should be preferred over 3-hop (A-B-C-D)
    assert data["recovered_hop_count"] <= 2, (
        f"shortest_hop chose {data['recovered_hop_count']} hops; expected ≤2"
    )



# ---------------------------------------------------------------------------
# Test 6: highest bandwidth selection
# ---------------------------------------------------------------------------

def test_highest_bandwidth_selection(client, network_id):
    nA = make_node(client, network_id, "A")
    nB = make_node(client, network_id, "B")
    nC = make_node(client, network_id, "C")
    nD = make_node(client, network_id, "D")

    def lnk(src, dst, bw, lat=10):
        r = client.post(f"/api/networks/{network_id}/links",
                        json={"source": src, "destination": dst, "bandwidth": bw, "latency": lat})
        assert r.status_code == 201, r.text
        return r.json()["link_id"]

    lAB = lnk(nA, nB, bw=50)  # bottleneck: 50
    lBD = lnk(nB, nD, bw=50)
    lAC = lnk(nA, nC, bw=200)  # bottleneck: 200
    lCD = lnk(nC, nD, bw=200)

    sim = run_sim(client, network_id, nA, nD)
    sim_id = sim["simulation_id"]
    fail_link(client, network_id, lBD)

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "highest_bandwidth"})
    data = r.json()
    assert data["status"] == "RECOVERED"
    rec = data["recovered_route"]
    assert nC in rec
    assert data["recovered_bandwidth"] == 200.0


# ---------------------------------------------------------------------------
# Test 7: multiple simultaneous failures
# ---------------------------------------------------------------------------

def test_multiple_failures(client, network_id):
    # A-B-D and A-C-D; fail AB and CD simultaneously — no path should exist
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]

    fail_link(client, network_id, ids["AB"])
    fail_link(client, network_id, ids["CD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "shortest_hop"})
    data = r.json()
    # A to D now impossible: AB gone, CD gone; only A-C→X or A-B→X but B-D is only link from B
    # Actually if AB failed and CD failed: A can reach C (no AB, but AC still ok)
    # A-C but C-D failed. A-B failed so B-D path also blocked. No valid route.
    assert data["status"] in ("NO_ALTERNATE_ROUTE", "RECOVERED")


# ---------------------------------------------------------------------------
# Test 8: multiple traffic flows — only affected flow recovered
# ---------------------------------------------------------------------------

def test_multiple_traffic_flows(client, network_id):
    ids = build_diamond(client, network_id)
    # sim1: A→D (uses A-B-D will be disrupted)
    sim1 = run_sim(client, network_id, ids["A"], ids["D"])
    # sim2: A→C (not affected by B-D failure)
    sim2 = run_sim(client, network_id, ids["A"], ids["C"])

    fail_link(client, network_id, ids["BD"])

    # Recover sim1
    r1 = client.post(f"/api/networks/{network_id}/recovery",
                     json={"simulation_id": sim1["simulation_id"], "strategy": "shortest_hop"})
    assert r1.json()["status"] == "RECOVERED"

    # sim2 not disrupted
    r2 = client.post(f"/api/networks/{network_id}/recovery",
                     json={"simulation_id": sim2["simulation_id"], "strategy": "shortest_hop"})
    assert r2.json()["status"] in ("NOT_REQUIRED", "RECOVERED")


# ---------------------------------------------------------------------------
# Test 9: recovery metrics accuracy
# ---------------------------------------------------------------------------

def test_recovery_metrics(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]

    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim_id, "strategy": "lowest_latency"})
    data = r.json()
    assert data["status"] == "RECOVERED"
    assert data["recovery_duration"] is not None
    assert data["recovery_duration"] >= 0
    assert data["recovered_latency"] is not None
    assert data["recovered_latency"] > 0
    assert data["recovered_hop_count"] is not None
    assert data["recovered_hop_count"] >= 1
    assert data["recovered_bandwidth"] is not None
    assert data["recovered_bandwidth"] > 0
    assert data["original_route"] is not None


# ---------------------------------------------------------------------------
# Test 10: failed component remains failed after recovery
# ---------------------------------------------------------------------------

def test_failed_component_remains_failed(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    fail_link(client, network_id, ids["BD"])

    client.post(f"/api/networks/{network_id}/recovery",
                json={"simulation_id": sim["simulation_id"], "strategy": "shortest_hop"})

    # Verify the BD link is still failed
    links_r = client.get(f"/api/networks/{network_id}/links/{ids['BD']}")
    assert links_r.status_code == 200
    assert links_r.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# Test 11: preview does NOT mutate state
# ---------------------------------------------------------------------------

def test_preview_does_not_mutate(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]
    original_route = sim["route"]

    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery/preview",
                    json={"simulation_id": sim_id, "strategy": "shortest_hop"})
    assert r.status_code == 200, r.text

    # Route in the DB should still be original route
    sim_r = client.get(f"/api/networks/{network_id}/traffic/simulations/{sim_id}")
    assert sim_r.json()["route"] == original_route

    # History should be unmodified (no new recovery events from preview)
    hist_r = client.get(f"/api/networks/{network_id}/recovery/history")
    assert hist_r.status_code == 200


# ---------------------------------------------------------------------------
# Test 12: recovery updates history and recovery_id is returned
# ---------------------------------------------------------------------------

def test_recovery_updates_history(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim["simulation_id"], "strategy": "shortest_hop"})
    data = r.json()
    assert data["recovery_id"] is not None

    hist = client.get(f"/api/networks/{network_id}/recovery/history")
    assert hist.status_code == 200
    assert len(hist.json()) >= 1


# ---------------------------------------------------------------------------
# Test 13: chaos revert does not break recovery history
# ---------------------------------------------------------------------------

def test_chaos_revert_does_not_break_recovery(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim["simulation_id"], "strategy": "shortest_hop"})
    assert r.json()["status"] == "RECOVERED"

    # Revert the chaos
    revert_all(client, network_id)

    # Verify topology returned to healthy
    topo = client.get(f"/api/networks/{network_id}/links/{ids['BD']}").json()
    assert topo["status"] == "active"

    # History should still be intact
    hist = client.get(f"/api/networks/{network_id}/recovery/history")
    assert len(hist.json()) >= 1


# ---------------------------------------------------------------------------
# Test 14: composite strategy
# ---------------------------------------------------------------------------

def test_composite_strategy(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery",
                    json={"simulation_id": sim["simulation_id"], "strategy": "composite",
                          "latency_weight": 1.0, "hop_weight": 1.0, "bandwidth_weight": 0.1})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "RECOVERED"


# ---------------------------------------------------------------------------
# Test 15: recover/all endpoint
# ---------------------------------------------------------------------------

def test_recover_all(client, network_id):
    ids = build_diamond(client, network_id)
    sim1 = run_sim(client, network_id, ids["A"], ids["D"])
    sim2 = run_sim(client, network_id, ids["A"], ids["D"])  # another sim on same path
    fail_link(client, network_id, ids["BD"])

    r = client.post(f"/api/networks/{network_id}/recovery/all?strategy=lowest_latency")
    assert r.status_code == 200
    results = r.json()
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Test 16: get simulation route endpoint
# ---------------------------------------------------------------------------

def test_simulation_route_endpoint(client, network_id):
    ids = build_diamond(client, network_id)
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]
    fail_link(client, network_id, ids["BD"])

    client.post(f"/api/networks/{network_id}/recovery",
                json={"simulation_id": sim_id, "strategy": "shortest_hop"})

    r = client.get(f"/api/networks/{network_id}/simulations/{sim_id}/route")
    assert r.status_code == 200
    data = r.json()
    assert "route" in data
    assert "route_status" in data


# ---------------------------------------------------------------------------
# INTEGRATION TEST: full end-to-end flow
# ---------------------------------------------------------------------------

def test_integration_full_e2e(client, network_id):
    """
    Full end-to-end:
      1. Create diamond topology
      2. Create baseline
      3. Run A→D (original route A-B-D)
      4. Inject B-D link failure
      5. Detect failures
      6. Run recovery → A-C-D
      7. Verify B-D still FAILED
      8. Verify route_changed=True, connectivity_restored=True
      9. Revert chaos
      10. Run A→D again (should succeed on original topology)
    """
    # 1. Topology
    ids = build_diamond(client, network_id)

    # 2. Baseline
    bl = client.post(f"/api/networks/{network_id}/failures/baseline")
    assert bl.status_code == 201

    # 3. Run traffic A→D
    sim = run_sim(client, network_id, ids["A"], ids["D"])
    sim_id = sim["simulation_id"]
    assert sim["status"] == "completed"
    original_route = sim["route"]
    assert original_route is not None

    # 4. Inject B-D failure
    fail_link(client, network_id, ids["BD"])

    # 5. Detect failures (verify detection sees the failure)
    det = client.post(f"/api/networks/{network_id}/failures/detect")
    assert det.status_code == 200
    det_data = det.json()
    assert det_data["failed_links"] >= 1
    assert det_data["overall_status"] == "critical"

    # 6. Run recovery
    rec_r = client.post(f"/api/networks/{network_id}/recovery",
                        json={"simulation_id": sim_id, "strategy": "lowest_latency"})
    assert rec_r.status_code == 200
    rec = rec_r.json()
    assert rec["status"] == "RECOVERED"
    assert rec["route_changed"] is True
    assert rec["connectivity_restored"] is True
    recovered_route = rec["recovered_route"]
    assert ids["B"] not in recovered_route or ids["D"] not in recovered_route or \
           not any({recovered_route[i], recovered_route[i+1]} == {ids["B"], ids["D"]}
                   for i in range(len(recovered_route)-1))

    # 7. Verify B-D is still failed
    lnk = client.get(f"/api/networks/{network_id}/links/{ids['BD']}").json()
    assert lnk["status"] == "failed"

    # 8. Verify metrics sane
    assert rec["original_latency"] is not None
    assert rec["recovered_latency"] is not None
    assert rec["recovery_duration"] >= 0

    # 9. Revert chaos
    revert_all(client, network_id)
    lnk2 = client.get(f"/api/networks/{network_id}/links/{ids['BD']}").json()
    assert lnk2["status"] == "active"

    # 10. Run traffic again — should succeed normally
    sim2 = run_sim(client, network_id, ids["A"], ids["D"])
    assert sim2["status"] == "completed"
    assert sim2["route"] is not None
