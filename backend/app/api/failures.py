"""REST endpoints for failure detection using MongoDB."""
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.errors import NotFoundError
from app.schemas.failures import (
    NetworkBaselineResponse, FailureDetectionResponse, AffectedTrafficReport, ConnectivityCheckResponse
)
from app.services.failure_detection_service import FailureDetectionService

router = APIRouter(prefix="/api/networks/{network_id}/failures", tags=["failure_detection"])

def get_service(db: Database = Depends(get_mongo_db)) -> FailureDetectionService:
    return FailureDetectionService(db)

@router.post("/baseline", response_model=NetworkBaselineResponse, status_code=201)
def create_baseline(network_id: str, service: FailureDetectionService = Depends(get_service)):
    return service.create_baseline(network_id)

@router.get("/baseline", response_model=NetworkBaselineResponse)
def get_baseline(network_id: str, service: FailureDetectionService = Depends(get_service)):
    return service.get_baseline(network_id)

@router.post("/detect", response_model=FailureDetectionResponse)
def detect_failures(network_id: str, service: FailureDetectionService = Depends(get_service)):
    return service.detect_failures(network_id)

@router.get("/report", response_model=FailureDetectionResponse)
def get_report(network_id: str, service: FailureDetectionService = Depends(get_service)):
    detection = service.get_report(network_id)
    if not detection:
        raise NotFoundError(f"No failure detection has been run for network '{network_id}'", "no_detection")
    return detection

@router.get("/history", response_model=list[FailureDetectionResponse])
def get_history(network_id: str, service: FailureDetectionService = Depends(get_service)):
    return service.get_history(network_id)

@router.get("/connectivity", response_model=ConnectivityCheckResponse)
def check_connectivity(network_id: str, source: str, destination: str, service: FailureDetectionService = Depends(get_service)):
    return service.check_connectivity(network_id, source, destination)

@router.get("/affected-traffic", response_model=AffectedTrafficReport)
def get_affected_traffic(network_id: str, service: FailureDetectionService = Depends(get_service)):
    return service.get_affected_traffic(network_id)
