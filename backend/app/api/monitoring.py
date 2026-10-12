"""REST API for Module 6 - Network Monitoring."""
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.services.monitoring_service import MonitoringService
from app.schemas.monitoring import (
    MonitoringSnapshot, SingleLinkMetrics, SingleNodeMetrics, RecoverySummary,
    TrafficMetricsSummary, ConnectivityMetrics
)

router = APIRouter(prefix="/api/networks/{network_id}/monitoring", tags=["monitoring"])

def get_service(db: Database = Depends(get_mongo_db)) -> MonitoringService:
    return MonitoringService(db)

@router.get("/current", response_model=dict)
def get_current(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_current_metrics(network_id)

@router.post("/snapshot", response_model=MonitoringSnapshot)
def create_snapshot(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.create_snapshot(network_id)

@router.get("/history", response_model=list[MonitoringSnapshot])
def get_history(network_id: str, limit: int = 50, service: MonitoringService = Depends(get_service)):
    return service.get_history(network_id, limit)

@router.get("/traffic", response_model=TrafficMetricsSummary)
def get_traffic(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_current_metrics(network_id)["traffic"]

@router.get("/latency", response_model=dict)
def get_latency(network_id: str, service: MonitoringService = Depends(get_service)):
    return {"average_latency": service.get_current_metrics(network_id)["traffic"]["average_latency"]}

@router.get("/packet-loss", response_model=dict)
def get_packet_loss(network_id: str, service: MonitoringService = Depends(get_service)):
    return {"packet_loss_percentage": service.get_current_metrics(network_id)["traffic"]["packet_loss_percentage"]}

@router.get("/throughput", response_model=dict)
def get_throughput(network_id: str, service: MonitoringService = Depends(get_service)):
    return {"throughput": service.get_current_metrics(network_id)["traffic"]["throughput"]}

@router.get("/connectivity", response_model=ConnectivityMetrics)
def get_connectivity(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_current_metrics(network_id)["connectivity"]

@router.get("/links", response_model=list[SingleLinkMetrics])
def get_links(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_links(network_id)

@router.get("/nodes", response_model=list[SingleNodeMetrics])
def get_nodes(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_nodes(network_id)

@router.get("/recovery", response_model=RecoverySummary)
def get_recovery_summary(network_id: str, service: MonitoringService = Depends(get_service)):
    return service.get_recovery_summary(network_id)
