"""REST endpoints for the chaos module using MongoDB."""
from fastapi import APIRouter, Depends, status
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.graph import graph_manager
from app.schemas.chaos import (
    ActiveChaosResponse, ApplyRequest, BandwidthReductionRequest, CongestionRequest, ExperimentResponse,
    HistoryResponse, LatencyRequest, LinkFailureRequest, MultiFailureRequest, PacketLossRequest, ResetResponse,
    RevertResponse, RouterFailureRequest,
)
from app.schemas.network import ErrorResponse
from app.services.chaos_service import ChaosService

router = APIRouter(
    prefix="/api/networks/{network_id}/chaos",
    tags=["chaos"],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid chaos parameters"},
        404: {"model": ErrorResponse, "description": "Network, node, link or experiment not found"},
        409: {"model": ErrorResponse, "description": "Target has already failed"},
    },
)

def get_service(db: Database = Depends(get_mongo_db)) -> ChaosService:
    return ChaosService(db, graph_manager)

_APPLIED = dict(response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)

@router.post("/router-failure", summary="Fail a router", **_APPLIED)
def router_failure(network_id: str, data: RouterFailureRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/link-failure", summary="Fail a link", **_APPLIED)
def link_failure(network_id: str, data: LinkFailureRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/packet-loss", summary="Set packet loss", **_APPLIED)
def packet_loss(network_id: str, data: PacketLossRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/latency", summary="Set latency", **_APPLIED)
def latency(network_id: str, data: LatencyRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/bandwidth-reduction", summary="Set bandwidth", **_APPLIED)
def bandwidth_reduction(network_id: str, data: BandwidthReductionRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/congestion", summary="Congest a link", **_APPLIED)
def congestion(network_id: str, data: CongestionRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/multi-failure", summary="Apply several events", **_APPLIED)
def multi_failure(network_id: str, data: MultiFailureRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.post("/apply", summary="Generic apply", **_APPLIED)
def apply(network_id: str, data: ApplyRequest, service: ChaosService = Depends(get_service)):
    return service.apply(network_id, data.to_experiment())

@router.get("/active", response_model=ActiveChaosResponse, response_model_exclude_none=True)
def active(network_id: str, service: ChaosService = Depends(get_service)):
    return service.active(network_id)

@router.get("/history", response_model=HistoryResponse)
def history(network_id: str, service: ChaosService = Depends(get_service)):
    return service.history(network_id)

@router.post("/reset", response_model=ResetResponse)
def reset(network_id: str, service: ChaosService = Depends(get_service)):
    return service.reset(network_id)

@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(network_id: str, experiment_id: str, service: ChaosService = Depends(get_service)):
    return service.get_experiment(network_id, experiment_id)

@router.post("/{experiment_id}/revert", response_model=RevertResponse)
def revert(network_id: str, experiment_id: str, service: ChaosService = Depends(get_service)):
    return service.revert(network_id, experiment_id)
