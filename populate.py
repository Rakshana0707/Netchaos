import urllib.request
import urllib.parse
import json
import time
import os

PORT = os.getenv("PORT", "8001")
BASE = f"http://localhost:{PORT}/api"

def req(url, method="GET", body=None):
    req_obj = urllib.request.Request(f"{BASE}{url}", method=method)
    if body is not None:
        req_obj.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    try:
        with urllib.request.urlopen(req_obj, data=data) as f:
            res = f.read()
            return json.loads(res) if res else None
    except urllib.error.HTTPError as e:
        print(f"Error {e.code} on {method} {url}: {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"Error on {method} {url}: {e}")
        return None

print(f"Connecting to NetChaos API on {BASE}...")
networks = req("/networks")
if not networks:
    print("No networks found. Exiting.")
    exit(1)

net = networks[0]
net_id = net["network_id"]
print(f"Using network: {net['name']} ({net_id})")

nodes = req(f"/networks/{net_id}/nodes") or []
links = req(f"/networks/{net_id}/links") or []

if len(nodes) < 2:
    print("Network needs at least 2 nodes. Exiting.")
    exit(1)

src_node = nodes[0]["node_id"]
dst_node = nodes[-1]["node_id"]
first_link = links[0]["link_id"] if links else None

print(f"\n--- 1. Running Real Traffic Simulation ({src_node} -> {dst_node}) ---")
traffic = req(f"/networks/{net_id}/traffic/simulations", "POST", {
    "source": src_node,
    "destination": dst_node,
    "packet_count": 1000,
    "packet_size": 1500,
    "store_packets": False
})
if traffic:
    sim_id = traffic.get("simulation_id")
    print(f"Created Traffic Simulation: {sim_id}")
    run_res = req(f"/networks/{net_id}/traffic/simulations/{sim_id}/run", "POST")
    print("Traffic Simulation Completed:", run_res.get("status") if run_res else "done")

if first_link:
    print(f"\n--- 2. Injecting Link Chaos on {first_link} ---")
    chaos = req(f"/networks/{net_id}/chaos/link-failure", "POST", {
        "link_id": first_link
    })
    if chaos:
        exp_id = chaos.get("experiment_id")
        print("Chaos Injected:", exp_id)
        
        print("\n--- 3. Capturing Telemetry Snapshot Under Chaos ---")
        monitoring = req(f"/networks/{net_id}/monitoring/snapshot", "POST")
        print("Monitoring captured:", monitoring.get("health_status") if monitoring else "captured")

        print("\n--- 4. Executing Dynamic Route Recovery ---")
        recovery = req(f"/networks/{net_id}/recovery/recover", "POST", {
            "strategy": "dijkstra_alternate",
            "simulation_id": traffic.get("simulation_id") if traffic else None
        })
        print("Recovery execution status:", recovery.get("status") if recovery else "processed")

        print(f"\n--- 5. Reverting Chaos on {first_link} ---")
        req(f"/networks/{net_id}/chaos/{exp_id}/revert", "POST")
        print("Chaos reverted to baseline.")

print("\n--- 6. Creating Baseline Monitoring Snapshot ---")
req(f"/networks/{net_id}/monitoring/snapshot", "POST")

print("\n--- 7. Running Automated Experiment Plan Suite ---")
plan = req("/experiment-plans", "POST", {
    "name": "NetChaos Resilience & Route Healing Benchmark",
    "description": "Dynamic automated resilience suite across active topology",
    "network_id": net_id,
    "target_simulations": [traffic['simulation_id']] if traffic else [],
    "chaos_events": [
        {"type": "link_failure", "link_id": first_link} if first_link else {"type": "node_failure", "node_id": src_node}
    ],
    "recovery_strategy": "dijkstra_alternate"
})
if plan:
    plan_id = plan.get("plan_id")
    print(f"Created Experiment Plan: {plan_id}")
    req(f"/experiment-plans/{plan_id}/run", "POST")
    print("Triggered Experiment Plan execution. Awaiting results...")
    time.sleep(2)

print("\n--- 8. Generating Research Benchmark Dataset ---")
dataset = req("/datasets", "POST", {
    "name": "Enterprise Mesh Resilience Benchmark v1.0",
    "version": "1.0",
    "description": "Benchmark telemetry dataset with automated traffic, chaos, and recovery traces",
    "filters": {}
})
if dataset:
    print("Dataset successfully generated:", dataset.get("metadata", {}).get("dataset_id"))

print("\n=== Populated NetChaos with Dynamic Benchmark Telemetry! ===")

