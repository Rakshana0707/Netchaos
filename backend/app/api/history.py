from fastapi import APIRouter, Depends
from typing import List
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.services.history_service import HistoryService
from app.schemas.history import ExperimentCreate, ExperimentResponse, ExperimentDetailResponse, PhaseLinks

router = APIRouter(tags=["history"])

def get_service(db: Database = Depends(get_mongo_db)) -> HistoryService:
    return HistoryService(db)

@router.post("/api/networks/{network_id}/experiments", response_model=ExperimentResponse)
def create_experiment(network_id: str, req: ExperimentCreate, svc: HistoryService = Depends(get_service)):
    return svc.create_experiment(network_id, req)

@router.post("/api/experiments/{experiment_id}/complete", response_model=ExperimentResponse)
def complete_experiment(experiment_id: str, svc: HistoryService = Depends(get_service)):
    return svc.complete_experiment(experiment_id)

@router.get("/api/networks/{network_id}/history", response_model=List[ExperimentResponse])
def get_history(network_id: str, limit: int = 50, svc: HistoryService = Depends(get_service)):
    return svc.get_experiments(network_id, limit)

@router.get("/api/experiments/{experiment_id}", response_model=ExperimentDetailResponse)
def get_experiment_detail(experiment_id: str, svc: HistoryService = Depends(get_service)):
    return svc.get_experiment_detail(experiment_id)

@router.post("/api/experiments/compare", response_model=List[dict])
def compare_experiments(experiment_ids: List[str], svc: HistoryService = Depends(get_service)):
    return svc.compare(experiment_ids)


@router.post("/api/experiments/{experiment_id}/phases", response_model=ExperimentResponse)
def link_phases(experiment_id: str, links: PhaseLinks, svc: HistoryService = Depends(get_service)):
    """Attach baseline / chaos / recovery / post-recovery records to an experiment so analytics can use them."""
    return svc.link_phases(experiment_id, links.model_dump(exclude_none=True))
