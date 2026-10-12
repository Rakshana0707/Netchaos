"""Business logic for failure detection using MongoDB."""
from pymongo.database import Database

from app.services.ids import next_id
from app.detection.failure_detector import FailureDetector
from app.enums import FailureType, NetworkStatus
from app.errors import NotFoundError, ConflictError
from app.schemas.failures import (
    NetworkBaselineResponse, FailureDetectionResponse, AffectedSimulationResponse, ConnectivityCheckResponse
)
from datetime import datetime, timezone

class FailureDetectionService:
    def __init__(self, db: Database):
        self.db = db

    def create_baseline(self, network_id: str) -> dict:
        network = self.db.networks.find_one({"id": network_id})
        if not network:
            raise NotFoundError(f"Network {network_id} not found", "network_not_found")

        self.db.network_baselines.update_many(
            {"network_id": network_id, "is_active": True},
            {"$set": {"is_active": False}}
        )

        old_baselines = list(self.db.network_baselines.find({"network_id": network_id}))
        prefix = f"baseline_{str(network_id)[-3:]}_"
        seq = len(old_baselines) + 1
        baseline_id = f"{prefix}{seq:03d}"

        baseline = {
            "id": baseline_id,
            "network_id": network_id,
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            "nodes": [],
            "links": []
        }
        
        nodes = list(self.db.nodes.find({"network_id": network_id}))
        for node in nodes:
            baseline["nodes"].append({
                "baseline_id": baseline_id,
                "node_id": node["id"],
                "status": node["status"]
            })

        links = list(self.db.links.find({"network_id": network_id}))
        for link in links:
            baseline["links"].append({
                "baseline_id": baseline_id,
                "link_id": link["id"],
                "status": link["status"],
                "bandwidth": link["bandwidth"],
                "latency": link["latency"],
                "packet_loss": link["packet_loss"]
            })
            
        self.db.network_baselines.insert_one(baseline)
        return baseline

    def get_baseline(self, network_id: str, auto_create: bool = False) -> dict:
        baseline = self.db.network_baselines.find_one(
            {"network_id": network_id, "is_active": True}, {"_id": 0}
        )
        if not baseline:
            if auto_create:
                return self.create_baseline(network_id)
            raise NotFoundError(f"Active baseline for network {network_id} not found", "baseline_not_found")
        return baseline

    def detect_failures(self, network_id: str, *, experiment_id: str | None = None) -> dict:
        baseline = self.get_baseline(network_id, auto_create=True)
        
        current_nodes = list(self.db.nodes.find({"network_id": network_id}))
        current_links = list(self.db.links.find({"network_id": network_id}))
        baseline_nodes = baseline["nodes"]
        baseline_links = baseline["links"]

        detector = FailureDetector(baseline_nodes, baseline_links, current_nodes, current_links)

        failed_nodes_data = detector.detect_failed_nodes()
        failed_links_data = detector.detect_failed_links()
        degraded_links_data = detector.detect_degraded_links()
        comp_count, components, partition_data = detector.detect_partitions()
        unreachable_pairs_count = detector.detect_unreachable_pairs()

        sims = list(self.db.traffic_simulations.find({
            "network_id": network_id,
            "status": "completed"
        }))
        for sim in sims:
            sim["route_nodes"] = sim.get("route", [])

        affected_sims_data = []
        if sims:
            affected_sims_data = detector.get_affected_simulations(sims) or []
            
        all_failures_data = failed_nodes_data + failed_links_data + degraded_links_data + partition_data

        overall_status = NetworkStatus.HEALTHY.value
        if failed_nodes_data or failed_links_data or partition_data:
            overall_status = NetworkStatus.CRITICAL.value
        elif degraded_links_data:
            overall_status = NetworkStatus.DEGRADED.value

        detection_id = next_id(self.db.failure_detections, {"network_id": network_id}, f"det_{str(network_id)[-3:]}_")

        detection = {
            "id": detection_id,
            "network_id": network_id,
            "baseline_id": baseline["id"],
            "experiment_id": experiment_id,
            "detected_at": datetime.now(timezone.utc),
            "overall_status": overall_status,
            "failed_nodes": len(failed_nodes_data),
            "failed_links": len(failed_links_data),
            "degraded_links": len(degraded_links_data),
            "connected_components": comp_count,
            "affected_simulations": len(affected_sims_data),
            "unreachable_pairs": unreachable_pairs_count,
            "failures": []
        }

        for idx, fd in enumerate(all_failures_data):
            detection["failures"].append({
                "id": f"fail_{detection_id.rsplit('_', 1)[-1]}_{idx+1:03d}",
                "network_id": network_id,
                "detection_id": detection["id"],
                "detected_at": datetime.now(timezone.utc),
                "failure_type": fd["failure_type"],
                "target_type": fd["target_type"],
                "target_id": fd.get("target_id", "network"),
                "severity": fd["severity"],
                "description": fd["description"],
                "status": "active"
            })
            
        self.db.failure_detections.insert_one(detection.copy())
        
        return detection

    def check_connectivity(self, network_id: str, source: str, destination: str) -> dict:
        baseline = self.get_baseline(network_id, auto_create=True)
        current_nodes = list(self.db.nodes.find({"network_id": network_id}))
        current_links = list(self.db.links.find({"network_id": network_id}))
        detector = FailureDetector(baseline["nodes"], baseline["links"], current_nodes, current_links)

        src_node = self.db.nodes.find_one({"id": source, "network_id": network_id})
        dest_node = self.db.nodes.find_one({"id": destination, "network_id": network_id})
        if not src_node:
            raise NotFoundError(f"Source Node {source} not found", "node_not_found")
        if not dest_node:
            raise NotFoundError(f"Destination Node {destination} not found", "node_not_found")

        reachable = detector.check_connectivity(source, destination)
        reason = "Destination is unreachable because the current network state is disconnected" if not reachable else None

        return {
            "source": source,
            "destination": destination,
            "reachable": reachable,
            "reason": reason
        }

    def get_history(self, network_id: str):
        return list(self.db.failure_detections.find({"network_id": network_id}, {"_id": 0}).sort("id", -1))

    def get_report(self, network_id: str):
        last_detection = self.db.failure_detections.find_one({"network_id": network_id}, sort=[("detected_at", -1)], projection={"_id": 0})
        return last_detection

    def get_affected_traffic(self, network_id: str):
        baseline = self.get_baseline(network_id, auto_create=True)
        current_nodes = list(self.db.nodes.find({"network_id": network_id}))
        current_links = list(self.db.links.find({"network_id": network_id}))
        detector = FailureDetector(baseline["nodes"], baseline["links"], current_nodes, current_links)
        
        sims = list(self.db.traffic_simulations.find({"network_id": network_id, "status": "completed"}))
        for sim in sims:
            sim["route_nodes"] = sim.get("route", [])
            
        affected = []
        if sims:
            affected = detector.get_affected_simulations(sims) or []
        return {"affected_simulations": affected}
