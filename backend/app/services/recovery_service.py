"""RecoveryService: coordinates failure detection, route selection, and persistence using MongoDB."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import networkx as nx
from pymongo.database import Database

from app.enums import ElementStatus
from app.errors import BadRequestError, NotFoundError
from app.recovery.recovery_engine import RecoveryEngine
from app.schemas.recovery import RecoveryRequest, RecoveryResponse, RecoveryStatus, RecoveryStrategy
from app.services.ids import next_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RecoveryService:
    """Orchestrates dynamic route recovery for a single network."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Public API methods
    # -------------------------------------------------------------------------

    def recover_simulation(
        self, network_id: str, req: RecoveryRequest, *,
        experiment_id: str | None = None, detection_id: str | None = None,
    ) -> RecoveryResponse:
        """Attempt to recover one simulation whose route has been disrupted by a failure.

        The simulation record itself is never modified: it keeps the measurements of the run that
        happened. The recovered route is stored in a recovery event; traffic over it is a *new*
        post-recovery simulation (``SimulationCreate.recovery_id``).
        """
        self._verify_network(network_id)
        sim = self._get_sim(network_id, req.simulation_id)

        start_ts = _utcnow()
        perf_start = time.monotonic()

        nodes = list(self.db.nodes.find({"network_id": network_id}))
        links = list(self.db.links.find({"network_id": network_id}))
        op_graph = self._build_operational_graph(nodes, links)

        original_route = sim.get("route") or []
        engine = RecoveryEngine(op_graph)

        if sim.get("status") != "completed" or not original_route:
            result = self._not_required(network_id, sim, start_ts, perf_start)
            self._persist(result, start_ts=start_ts, experiment_id=experiment_id, detection_id=detection_id)
            return result

        orig_latency, orig_hops, orig_bw = engine.compute_route_metrics(original_route)
        if sim.get("path_latency_ms") is not None:
            orig_latency = sim["path_latency_ms"]
        if sim.get("hop_count") is not None:
            orig_hops = sim["hop_count"]
        if sim.get("path_bandwidth_mbps") is not None:
            orig_bw = sim["path_bandwidth_mbps"]

        if engine.is_route_valid(original_route):
            result = self._not_required(network_id, sim, start_ts, perf_start,
                                        original_route=original_route,
                                        orig_latency=orig_latency,
                                        orig_hops=orig_hops,
                                        orig_bw=orig_bw)
            self._persist(result, start_ts=start_ts, experiment_id=experiment_id, detection_id=detection_id)
            return result

        source = sim["source_node_id"]
        destination = sim["destination_node_id"]
        candidate = engine.find_best_route(
            source, destination, req.strategy,
            req.latency_weight, req.hop_weight, req.bandwidth_weight
        )

        end_ts = _utcnow()
        duration = time.monotonic() - perf_start

        if candidate is None:
            result = RecoveryResponse(
                network_id=network_id,
                simulation_id=req.simulation_id,
                status=RecoveryStatus.NO_ALTERNATE_ROUTE,
                original_route=original_route,
                recovered_route=None,
                route_changed=False,
                original_latency=orig_latency,
                recovered_latency=None,
                original_hop_count=orig_hops,
                recovered_hop_count=None,
                original_bandwidth=orig_bw,
                recovered_bandwidth=None,
                recovery_duration=round(duration, 6),
                connectivity_restored=False,
                failure_type="route_unavailable",
                failure_description=(
                    f"No alternate route from {source} to {destination} with current failures"
                ),
            )
        else:
            connectivity_restored = nx.has_path(op_graph, source, destination)
            result = RecoveryResponse(
                network_id=network_id,
                simulation_id=req.simulation_id,
                status=RecoveryStatus.RECOVERED,
                original_route=original_route,
                recovered_route=candidate.path,
                route_changed=(candidate.path != original_route),
                original_latency=orig_latency,
                recovered_latency=round(candidate.latency, 6),
                original_hop_count=orig_hops,
                recovered_hop_count=candidate.hop_count,
                original_bandwidth=orig_bw,
                recovered_bandwidth=round(candidate.bandwidth, 6),
                recovery_duration=round(duration, 6),
                connectivity_restored=connectivity_restored,
                failure_type="route_unavailable",
                failure_description=(
                    f"Route {' -> '.join(original_route)} disrupted; recovered via "
                    f"{' -> '.join(candidate.path)}"
                ),
            )

        self._persist(result, start_ts=start_ts, experiment_id=experiment_id, detection_id=detection_id)
        return result

    def recover_all(self, network_id: str, strategy: RecoveryStrategy) -> list[RecoveryResponse]:
        self._verify_network(network_id)
        sims = list(self.db.traffic_simulations.find({
            "network_id": network_id,
            "status": "completed"
        }))

        nodes = list(self.db.nodes.find({"network_id": network_id}))
        links = list(self.db.links.find({"network_id": network_id}))
        op_graph = self._build_operational_graph(nodes, links)
        engine = RecoveryEngine(op_graph)

        results = []
        for sim in sims:
            route = sim.get("route") or []
            if not route:
                continue
            if engine.is_route_valid(route):
                continue
            req = RecoveryRequest(simulation_id=sim["id"], strategy=strategy)
            result = self.recover_simulation(network_id, req)
            results.append(result)
        return results

    def preview_recovery(self, network_id: str, req: RecoveryRequest) -> RecoveryResponse:
        self._verify_network(network_id)
        sim = self._get_sim(network_id, req.simulation_id)

        nodes = list(self.db.nodes.find({"network_id": network_id}))
        links = list(self.db.links.find({"network_id": network_id}))
        op_graph = self._build_operational_graph(nodes, links)
        engine = RecoveryEngine(op_graph)

        perf_start = time.monotonic()
        original_route = sim.get("route") or []
        orig_latency = sim.get("path_latency_ms") or 0.0
        orig_hops = sim.get("hop_count") or 0
        orig_bw = sim.get("path_bandwidth_mbps") or 0.0

        source = sim["source_node_id"]
        destination = sim["destination_node_id"]
        candidate = engine.find_best_route(
            source, destination, req.strategy,
            req.latency_weight, req.hop_weight, req.bandwidth_weight
        )
        duration = time.monotonic() - perf_start

        if candidate is None:
            return RecoveryResponse(
                network_id=network_id,
                simulation_id=req.simulation_id,
                status=RecoveryStatus.NO_ALTERNATE_ROUTE,
                original_route=original_route,
                recovered_route=None,
                route_changed=False,
                original_latency=orig_latency,
                original_hop_count=orig_hops,
                original_bandwidth=orig_bw,
                recovery_duration=round(duration, 6),
                connectivity_restored=False,
            )

        return RecoveryResponse(
            network_id=network_id,
            simulation_id=req.simulation_id,
            status=RecoveryStatus.RECOVERED,
            original_route=original_route,
            recovered_route=candidate.path,
            route_changed=(candidate.path != original_route),
            original_latency=orig_latency,
            recovered_latency=round(candidate.latency, 6),
            original_hop_count=orig_hops,
            recovered_hop_count=candidate.hop_count,
            original_bandwidth=orig_bw,
            recovered_bandwidth=round(candidate.bandwidth, 6),
            recovery_duration=round(duration, 6),
            connectivity_restored=nx.has_path(op_graph, source, destination),
        )

    def get_history(self, network_id: str) -> list[dict]:
        self._verify_network(network_id)
        return list(self.db.recovery_events.find({"network_id": network_id}).sort("created_at", -1))

    def get_event(self, network_id: str, recovery_id: str) -> dict:
        ev = self.db.recovery_events.find_one({"id": recovery_id, "network_id": network_id})
        if ev is None:
            raise NotFoundError(f"Recovery event '{recovery_id}' not found", "recovery_not_found")
        return ev

    def get_simulation_route(self, network_id: str, simulation_id: str) -> dict:
        sim = self._get_sim(network_id, simulation_id)
        latest = self.db.recovery_events.find_one(
            {
                "network_id": network_id,
                "simulation_id": simulation_id,
                "recovery_status": RecoveryStatus.RECOVERED.value
            },
            sort=[("created_at", -1)]
        )
        if latest and latest.get("recovered_route"):
            return {
                "simulation_id": simulation_id,
                "route": latest["recovered_route"],
                "route_status": "RECOVERED",
            }
        return {
            "simulation_id": simulation_id,
            "route": sim.get("route"),
            "route_status": sim["status"].upper() if sim.get("route") else "NO_ROUTE",
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _build_operational_graph(self, nodes: list, links: list) -> nx.Graph:
        """Build a NetworkX graph containing only active nodes and active links."""
        G = nx.Graph()
        active_nodes = {n["id"] for n in nodes if n["status"] == ElementStatus.ACTIVE.value}
        for nid in active_nodes:
            G.add_node(nid)
        for link in links:
            if link["status"] != ElementStatus.ACTIVE.value:
                continue
            if link["source_node_id"] not in active_nodes or link["destination_node_id"] not in active_nodes:
                continue
            G.add_edge(
                link["source_node_id"],
                link["destination_node_id"],
                link_id=link["id"],
                bandwidth=link["bandwidth"],
                latency=link["latency"],
                packet_loss=link["packet_loss"],
            )
        return G

    def _verify_network(self, network_id: str) -> None:
        if self.db.networks.find_one({"id": network_id}) is None:
            raise NotFoundError(f"Network '{network_id}' not found", "network_not_found")

    def _get_sim(self, network_id: str, simulation_id: str) -> dict:
        sim = self.db.traffic_simulations.find_one({"id": simulation_id, "network_id": network_id})
        if sim is None:
            raise NotFoundError(
                f"Simulation '{simulation_id}' not found in network '{network_id}'",
                "simulation_not_found",
            )
        return sim

    def _not_required(
        self,
        network_id: str,
        sim: dict,
        start_ts: datetime,
        perf_start: float,
        *,
        original_route: list | None = None,
        orig_latency: float = 0.0,
        orig_hops: int = 0,
        orig_bw: float = 0.0,
    ) -> RecoveryResponse:
        return RecoveryResponse(
            network_id=network_id,
            simulation_id=sim["id"],
            status=RecoveryStatus.NOT_REQUIRED,
            original_route=original_route or sim.get("route"),
            recovered_route=None,
            route_changed=False,
            original_latency=orig_latency,
            original_hop_count=orig_hops,
            original_bandwidth=orig_bw,
            recovery_duration=round(time.monotonic() - perf_start, 6),
            connectivity_restored=False,
        )

    def _next_recovery_id(self, network_id: str) -> str:
        return next_id(self.db.recovery_events, {"network_id": network_id}, f"rec_{network_id[-3:]}_")

    def _persist(
        self, result: RecoveryResponse, *, start_ts: datetime | None = None,
        experiment_id: str | None = None, detection_id: str | None = None,
    ) -> None:
        rec_id = self._next_recovery_id(result.network_id)
        end_ts = _utcnow()
        detection = self._find_detection(result.network_id, detection_id)
        recovered = result.status == RecoveryStatus.RECOVERED
        # Documented recovery time: from the detection of the failure until an alternative route was
        # provisioned (simulator wall-clock, seconds). Only defined when a detection exists and recovery succeeded.
        recovery_time = None
        if recovered and detection and detection.get("detected_at"):
            detected_at = detection["detected_at"].replace(tzinfo=None)
            recovery_time = round(max((end_ts - detected_at).total_seconds(), 0.0), 6)
        event = {
            "id": rec_id,
            "network_id": result.network_id,
            "simulation_id": result.simulation_id,
            "experiment_id": experiment_id,
            "failure_detection_id": detection["id"] if detection else None,
            "original_route": result.original_route,
            "recovered_route": result.recovered_route,
            "original_latency": result.original_latency,
            "recovered_latency": result.recovered_latency,
            "original_hop_count": result.original_hop_count,
            "recovered_hop_count": result.recovered_hop_count,
            "original_bandwidth": result.original_bandwidth,
            "recovered_bandwidth": result.recovered_bandwidth,
            "route_changed": result.route_changed,
            "recovery_status": result.status.value,
            "recovery_start_time": start_ts or end_ts,
            "recovery_end_time": end_ts,
            "recovery_duration": result.recovery_duration,
            "recovery_time_seconds": recovery_time,
            "failure_type": result.failure_type,
            "failure_description": result.failure_description,
            "created_at": end_ts,
        }
        self.db.recovery_events.insert_one(event)
        result.recovery_id = rec_id

    def _find_detection(self, network_id: str, detection_id: str | None) -> dict | None:
        """The detection that observed the failure: the given one, else the network's latest sweep."""
        if detection_id:
            return self.db.failure_detections.find_one({"id": detection_id, "network_id": network_id})
        return self.db.failure_detections.find_one({"network_id": network_id}, sort=[("detected_at", -1)])
