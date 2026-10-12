from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database
from typing import List

from app.database.database import get_mongo_db
from app.schemas.analytics import (
    AnalyticsSummaryResponse, FailureRanking, AnalyticsComparisonResponse,
    CompareRequest, ResearchReport
)
from app.services.resilience_analytics_service import ResilienceAnalyticsService
from app.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["Analytics"])

def get_analytics_service(db: Database = Depends(get_mongo_db)) -> ResilienceAnalyticsService:
    return ResilienceAnalyticsService(db)

@router.get("/networks/{network_id}/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_network_analytics_summary(network_id: str, svc: ResilienceAnalyticsService = Depends(get_analytics_service)):
    try:
        return svc.get_network_analytics_summary(network_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/networks/{network_id}/analytics/failures", response_model=List[FailureRanking])
def get_network_failure_ranking(network_id: str, svc: ResilienceAnalyticsService = Depends(get_analytics_service)):
    try:
        return svc.get_failure_ranking(network_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/analytics/compare", response_model=AnalyticsComparisonResponse)
def compare_experiments(req: CompareRequest, svc: ResilienceAnalyticsService = Depends(get_analytics_service)):
    return svc.compare_experiments(req)

@router.get("/experiments/{experiment_id}/report", response_model=ResearchReport)
def get_experiment_report(experiment_id: str, svc: ResilienceAnalyticsService = Depends(get_analytics_service)):
    try:
        return svc.generate_experiment_report(experiment_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/experiments/{experiment_id}/configuration")
def get_experiment_configuration(experiment_id: str, svc: ResilienceAnalyticsService = Depends(get_analytics_service)):
    try:
        return svc.export_experiment_configuration(experiment_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

