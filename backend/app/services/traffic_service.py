"""Business logic for traffic simulations using MongoDB."""
import secrets
import time
from datetime import datetime, timezone
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.config import get_max_stored_packets
from app.enums import PacketStatus, SimulationStatus
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.graph import GraphManager
from app.schemas.traffic import SimulationCreate
from app.services.ids import next_id
from app.services.topology_service import TopologyService
from app.simulation.traffic_simulator import RouteUnavailableError, SimulationOutcome, TrafficMetrics, TrafficSimulator

_INSERT_CHUNK = 500

def _now():
    return datetime.now(timezone.utc)

class TrafficService:
    def __init__(self, db: Database, graphs: GraphManager) -> None:
        self.db = db
        self.topology = TopologyService(db, graphs)

    def create_simulation(
        self, network_id: str, data: SimulationCreate, *, phase: str | None = None, experiment_id: str | None = None,
    ) -> dict:
        """Create a pending simulation. ``phase``/``experiment_id`` tag it as part of an experiment lifecycle."""
        self.topology.get_network(network_id, lock=True)
        for role, node_id in (("Source", data.source), ("Destination", data.destination)):
            if not self.db.nodes.find_one({"id": node_id, "network_id": network_id}):
                raise NotFoundError(f"{role} node '{node_id}' not found in network '{network_id}'", "node_not_found")
        if data.source == data.destination:
            raise BadRequestError("Source and destination must be different nodes", "same_source_destination")

        limit = get_max_stored_packets()
        if data.store_packets and data.packet_count > limit:
            raise BadRequestError(f"store_packets is only allowed for simulations of up to {limit} packets", "invalid_store_packets")

        requested_route = None
        if data.recovery_id:
            requested_route = self._recovered_route(network_id, data)
            phase = phase or "post_recovery"

        seed = data.random_seed if data.random_seed is not None else secrets.randbelow(2**32)
        sim = {
            "id": next_id(self.db.traffic_simulations, {"network_id": network_id}, "sim_"),
            "network_id": network_id,
            "source_node_id": data.source,
            "destination_node_id": data.destination,
            "packet_count": data.packet_count,
            "packet_size": data.packet_size,
            "random_seed": seed,
            "store_packets": data.store_packets,
            "status": SimulationStatus.PENDING.value,
            "phase": phase,
            "recovery_id": data.recovery_id,
            "experiment_id": experiment_id,
            "requested_route": requested_route,
            "created_at": _now()
        }

        try:
            self.db.traffic_simulations.insert_one(sim)
        except DuplicateKeyError:
            raise ConflictError("The change conflicts with existing data")
        return sim

    def _recovered_route(self, network_id: str, data: SimulationCreate) -> list[str]:
        """The route of a RECOVERED recovery event, checked against the requested source/destination."""
        event = self.db.recovery_events.find_one({"id": data.recovery_id, "network_id": network_id})
        if event is None:
            raise NotFoundError(f"Recovery event '{data.recovery_id}' not found in network '{network_id}'", "recovery_not_found")
        route = event.get("recovered_route")
        if event.get("recovery_status") != "RECOVERED" or not route:
            raise ConflictError(
                f"Recovery event '{data.recovery_id}' did not produce a route (status {event.get('recovery_status')})",
                "recovery_not_usable",
            )
        if route[0] != data.source or route[-1] != data.destination:
            raise BadRequestError(
                f"Recovered route runs {route[0]} -> {route[-1]}, not {data.source} -> {data.destination}", "route_mismatch",
            )
        return list(route)

    def list_simulations(self, network_id: str) -> list[dict]:
        self.topology.get_network(network_id)
        return list(self.db.traffic_simulations.find({"network_id": network_id}, {"_id": 0}).sort("id", -1))

    def get_simulation(self, network_id: str, simulation_id: str) -> dict:
        self.topology.get_network(network_id)
        sim = self.db.traffic_simulations.find_one({"id": simulation_id, "network_id": network_id}, {"_id": 0})
        if not sim:
            raise NotFoundError(f"Simulation '{simulation_id}' not found in network '{network_id}'", "simulation_not_found")
        return sim

    def get_metrics(self, network_id: str, simulation_id: str) -> dict:
        sim = self.get_simulation(network_id, simulation_id)
        if sim["status"] in (SimulationStatus.PENDING.value, SimulationStatus.RUNNING.value):
            raise ConflictError(f"Simulation '{simulation_id}' is {sim['status']}; metrics exist once it has run", "metrics_not_available")
        return sim

    def list_packets(self, network_id: str, simulation_id: str, limit: int, offset: int) -> tuple[int, list[dict]]:
        sim = self.get_simulation(network_id, simulation_id)
        where = {"simulation_id": sim["id"], "network_id": network_id}
        total = self.db.packets.count_documents(where)
        rows = list(self.db.packets.find(where, {"_id": 0}).sort("sequence_number", 1).skip(offset).limit(limit))
        return total, rows

    def run_simulation(self, network_id: str, simulation_id: str) -> dict:
        sim = self.get_simulation(network_id, simulation_id)
        self._claim(sim)
        try:
            simulator = TrafficSimulator(self.topology.snapshot_graph(network_id))
            wall_start = time.perf_counter()
            try:
                outcome = simulator.simulate_traffic(
                    sim["source_node_id"], sim["destination_node_id"], sim["packet_count"], sim["packet_size"],
                    sim["random_seed"], keep_packets=sim["store_packets"], route=sim.get("requested_route"),
                )
            except RouteUnavailableError as exc:
                self._save_failure(sim, str(exc), (time.perf_counter() - wall_start) * 1000)
                return self.get_simulation(network_id, simulation_id)
                
            execution_ms = (time.perf_counter() - wall_start) * 1000
            self._save_success(sim, outcome, simulator.calculate_metrics(outcome), execution_ms)
        except Exception as exc:
            self.db.traffic_simulations.update_one(
                {"id": sim["id"], "network_id": network_id},
                {"$set": {
                    "status": SimulationStatus.FAILED.value, 
                    "completed_at": _now(),
                    "failure_reason": f"Simulation error: {type(exc).__name__}"[:255]
                }}
            )
            raise
        return self.get_simulation(network_id, simulation_id)

    def _claim(self, sim: dict) -> None:
        result = self.db.traffic_simulations.update_one(
            {"id": sim["id"], "network_id": sim["network_id"], "status": SimulationStatus.PENDING.value},
            {"$set": {"status": SimulationStatus.RUNNING.value, "started_at": _now()}}
        )
        if result.modified_count > 0:
            return
            
        current = self.db.traffic_simulations.find_one({"id": sim["id"], "network_id": sim["network_id"]})
        if current and current["status"] == SimulationStatus.RUNNING.value:
            raise ConflictError(f"Simulation '{sim['id']}' is already running", "simulation_already_running")
            
        raise ConflictError(
            f"Simulation '{sim['id']}' has already finished ({current['status'] if current else 'unknown'}). "
            "Create a new simulation to run again; results of finished simulations are kept unchanged.",
            "simulation_already_finished"
        )

    def _save_failure(self, sim: dict, reason: str, execution_ms: float) -> None:
        self.db.traffic_simulations.update_one(
            {"id": sim["id"], "network_id": sim["network_id"]},
            {"$set": {
                "status": SimulationStatus.FAILED.value,
                "failure_reason": reason,
                "route_available": False,
                "execution_duration_ms": execution_ms,
                "completed_at": _now()
            }}
        )

    def _save_success(self, sim: dict, outcome: SimulationOutcome, metrics: TrafficMetrics, execution_ms: float) -> None:
        info = outcome.route_info
        update_data = {
            "status": SimulationStatus.COMPLETED.value,
            "route_available": True,
            "route": info.route,
            "delivered_packets": metrics.delivered_packets,
            "dropped_packets": metrics.dropped_packets,
            "packet_loss_percentage": metrics.packet_loss_percentage,
            "path_latency_ms": metrics.path_latency_ms,
            "hop_count": metrics.hop_count,
            "path_bandwidth_mbps": metrics.path_bandwidth_mbps,
            "throughput_mbps": metrics.throughput_mbps,
            "simulated_duration_ms": metrics.simulated_duration_ms,
            "execution_duration_ms": execution_ms,
            "completed_at": _now()
        }
        self.db.traffic_simulations.update_one(
            {"id": sim["id"], "network_id": sim["network_id"]},
            {"$set": update_data}
        )
        
        if outcome.packets:
            now = _now()
            rows = [
                {
                    "simulation_id": sim["id"], "network_id": sim["network_id"], "sequence_number": p.sequence_number,
                    "packet_id": f"pkt_{p.sequence_number:03d}", "source_node_id": sim["source_node_id"],
                    "destination_node_id": sim["destination_node_id"], "packet_size": sim["packet_size"],
                    "status": p.status.value, "route": info.route, "dropped_at_link_id": p.dropped_at_link_id,
                    "completed_at_ms": p.completed_at_ms, "created_at": now,
                }
                for p in outcome.packets
            ]
            for start in range(0, len(rows), _INSERT_CHUNK):
                self.db.packets.insert_many(rows[start:start + _INSERT_CHUNK])
