import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_canonical_e2e_workflow():
    # 1. Create Network
    res = client.post("/api/networks", json={"name": "Canonical Test Net", "description": "E2E Integration"})
    assert res.status_code in (200, 201)
    net_id = res.json()["network_id"]
    
    try:
        # 2. Configure Topology (A, B, C, D)
        for node in ["A", "B", "C", "D"]:
            client.post(f"/api/networks/{net_id}/nodes", json={"name": f"Node {node}", "type": "router"})
            
        # Get Node IDs
        topo_res = client.get(f"/api/networks/{net_id}/topology")
        nodes_ref = {n["name"]: n["id"] for n in topo_res.json()["nodes"]}
        
        # Create Links A-B(10ms), B-D(10ms), A-C(20ms), C-D(20ms)
        links_to_create = [
            (nodes_ref["Node A"], nodes_ref["Node B"], 100, 10),
            (nodes_ref["Node B"], nodes_ref["Node D"], 100, 10),
            (nodes_ref["Node A"], nodes_ref["Node C"], 100, 20), # higher latency alternative
            (nodes_ref["Node C"], nodes_ref["Node D"], 100, 20)
        ]
        
        for src, dest, bw, lat in links_to_create:
            client.post(f"/api/networks/{net_id}/links", json={
                "source": src, "destination": dest, "bandwidth": bw, "latency": lat, "packet_loss": 0.0
            })
            
        topo_res = client.get(f"/api/networks/{net_id}/topology")
        links_ref = {f"{l['source']}-{l['destination']}": l["id"] for l in topo_res.json()["links"]}
        bd_link_id = None
        for link in topo_res.json()["links"]:
            if (link["source"] == nodes_ref["Node B"] and link["destination"] == nodes_ref["Node D"]) or \
               (link["source"] == nodes_ref["Node D"] and link["destination"] == nodes_ref["Node B"]):
                bd_link_id = link["id"]
        assert bd_link_id is not None
        
        def spawn_and_run_traffic():
            traf_res = client.post(f"/api/networks/{net_id}/traffic/simulations", json={
                "source": nodes_ref["Node A"], "destination": nodes_ref["Node D"], 
                "packet_count": 100, "packet_size": 1024, "protocol": "TCP"
            })
            assert traf_res.status_code < 300, traf_res.json()
            s_id = traf_res.json()["simulation_id"]
            run_res = client.post(f"/api/networks/{net_id}/traffic/simulations/{s_id}/run")
            assert run_res.status_code < 300, run_res.json()
            return s_id, run_res.json()

        # 4. Run Baseline Traffic
        sim_id, base_metrics = spawn_and_run_traffic()
        assert base_metrics["delivered_packets"] == 100
        assert base_metrics["path_latency_ms"] == 20.0 # A-B (10) + B-D (10)
        
        # Create Failure Detection Baseline
        base_res = client.post(f"/api/networks/{net_id}/failures/baseline")
        assert base_res.status_code < 300
    
        # 5. Start Experiment Lifecycle
        exp_res = client.post(f"/api/networks/{net_id}/experiments", json={"name": "E2E Sim", "description": "Test"})
        exp_id = exp_res.json()["id"]
        
        # 6. Inject Chaos (Fail B-D)
        chaos_res = client.post(f"/api/networks/{net_id}/chaos/link-failure", json={
            "link_id": bd_link_id
        })
        assert chaos_res.status_code < 300, chaos_res.json()
        chaos_exp_id = chaos_res.json()["experiment_id"]
        
        # Verify topology reflects it
        topo_res = client.get(f"/api/networks/{net_id}/topology")
        failed_link = next(l for l in topo_res.json()["links"] if l["id"] == bd_link_id)
        assert failed_link["status"] == "failed"
        # Run traffic after chaos -> should drop all packets
        fail_sim_id, fail_metrics = spawn_and_run_traffic()
        assert fail_metrics.get("delivered_packets") in (0, None)
        assert fail_metrics["status"] == "failed"
        
        # 7. Detect Failure
        detect_res = client.post(f"/api/networks/{net_id}/failures/detect")
        assert detect_res.status_code < 300, detect_res.json()
        failures = detect_res.json()
        assert failures["overall_status"] == "critical"
        assert failures["failed_links"] == 1
        
        # 8. Preview Recovery
        preview_res = client.post(f"/api/networks/{net_id}/recovery/preview", json={"simulation_id": sim_id, "strategy": "shortest_hop"})
        assert preview_res.json()["status"] == "RECOVERED"
        assert len(preview_res.json()["recovered_route"]) > 0
        
        # 9. Execute Recovery
        recovery_res = client.post(f"/api/networks/{net_id}/recovery", json={"simulation_id": sim_id, "strategy": "shortest_hop"})
        assert recovery_res.json()["status"] == "RECOVERED"
        
        # 10. Verify Recovered Simulation
        rec_sim_res = client.get(f"/api/networks/{net_id}/traffic/simulations/{sim_id}")
        rec_sim = rec_sim_res.json()
        assert rec_sim["route_available"] == True
        assert len(rec_sim["route"]) > 0
        
        # 11. Monitoring Verification
        mon_res = client.get(f"/api/networks/{net_id}/monitoring/current")
        assert mon_res.json()["health_status"] == "CRITICAL" # Because a link is failed
        
        # 12. Revert Chaos
        client.post(f"/api/networks/{net_id}/chaos/{chaos_exp_id}/revert")
        
        # Verify topology returned to normal
        topo_res = client.get(f"/api/networks/{net_id}/topology")
        restored_link = next(l for l in topo_res.json()["links"] if l["id"] == bd_link_id)
        assert restored_link["status"] == "active"
        
        # Run traffic again, should return to 20ms baseline!
        _, restored_metrics = spawn_and_run_traffic()
        assert restored_metrics["path_latency_ms"] == 20.0
        
        # 13. Complete Experiment
        client.post(f"/api/experiments/{exp_id}/complete")
        
        # Fetch History
        hist_res = client.get(f"/api/experiments/{exp_id}")
        assert hist_res.json()["experiment"]["status"] == "COMPLETED"
        assert len(hist_res.json()["timeline"]) > 0
        
        print("E2E Integration Successful!")
    finally:
        client.delete(f"/api/networks/{net_id}")
