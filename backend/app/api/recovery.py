"""REST API for Module 5 — Dynamic Recovery using MongoDB."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.schemas.recovery import (
    RecoveryRequest,
    RecoveryResponse,
    RecoveryStrategy,
    RoutePreviewRequest,
    SimulationRouteResponse,
)
from app.services.recovery_service import RecoveryService

router = APIRouter(tags=["recovery"])


def _svc(db: Database = Depends(get_mongo_db)) -> RecoveryService:
    return RecoveryService(db)


# ── per-network endpoints ────────────────────────────────────────────────────

@router.post(
    "/api/networks/{network_id}/recovery",
    response_model=RecoveryResponse,
    summary="Recover a single simulation's route after a failure",
)
def recover_simulation(
    network_id: str, req: RecoveryRequest, svc: RecoveryService = Depends(_svc)
) -> RecoveryResponse:
    return svc.recover_simulation(network_id, req)


@router.post(
    "/api/networks/{network_id}/recovery/all",
    response_model=list[RecoveryResponse],
    summary="Recover all affected simulations",
)
def recover_all(
    network_id: str,
    strategy: RecoveryStrategy = RecoveryStrategy.LOWEST_LATENCY,
    svc: RecoveryService = Depends(_svc),
) -> list[RecoveryResponse]:
    return svc.recover_all(network_id, strategy)


@router.post(
    "/api/networks/{network_id}/recovery/preview",
    response_model=RecoveryResponse,
    summary="Preview an alternative route without executing recovery",
)
def preview_recovery(
    network_id: str, req: RoutePreviewRequest, svc: RecoveryService = Depends(_svc)
) -> RecoveryResponse:
    return svc.preview_recovery(network_id, req)


@router.get(
    "/api/networks/{network_id}/recovery/history",
    response_model=list[RecoveryResponse],
    summary="List recovery events for a network",
)
def get_history(
    network_id: str, svc: RecoveryService = Depends(_svc)
) -> list[RecoveryResponse]:
    events = svc.get_history(network_id)
    return [_event_to_response(e) for e in events]


@router.get(
    "/api/networks/{network_id}/recovery/{recovery_id}",
    response_model=RecoveryResponse,
    summary="Get a specific recovery event",
)
def get_event(
    network_id: str, recovery_id: str, svc: RecoveryService = Depends(_svc)
) -> RecoveryResponse:
    ev = svc.get_event(network_id, recovery_id)
    return _event_to_response(ev)


# ── simulation route ────────────────────────────────────────────────────────

@router.get(
    "/api/networks/{network_id}/simulations/{simulation_id}/route",
    response_model=SimulationRouteResponse,
    summary="Get the current (possibly recovered) route for a simulation",
)
def get_simulation_route(
    network_id: str, simulation_id: str, svc: RecoveryService = Depends(_svc)
) -> SimulationRouteResponse:
    data = svc.get_simulation_route(network_id, simulation_id)
    return SimulationRouteResponse(**data)


# ── helpers ─────────────────────────────────────────────────────────────────

def _event_to_response(ev: dict) -> RecoveryResponse:
    from app.schemas.recovery import RecoveryStatus
    return RecoveryResponse(
        recovery_id=ev["id"],
        network_id=ev["network_id"],
        simulation_id=ev["simulation_id"],
        status=RecoveryStatus(ev["recovery_status"]),
        failure_type=ev.get("failure_type"),
        failure_description=ev.get("failure_description"),
        original_route=ev.get("original_route"),
        recovered_route=ev.get("recovered_route"),
        route_changed=ev.get("route_changed", False),
        original_latency=ev.get("original_latency"),
        recovered_latency=ev.get("recovered_latency"),
        original_hop_count=ev.get("original_hop_count"),
        recovered_hop_count=ev.get("recovered_hop_count"),
        original_bandwidth=ev.get("original_bandwidth"),
        recovered_bandwidth=ev.get("recovered_bandwidth"),
        recovery_duration=ev.get("recovery_duration"),
        connectivity_restored=(ev["recovery_status"] == "RECOVERED"),
    )
