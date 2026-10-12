from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from pymongo.database import Database
import csv
import io
import json

from app.database.database import get_mongo_db
from app.schemas.runner import ExperimentPlanCreate, ExperimentPlanResponse
from app.services.runner_service import RunnerService
from app.errors import NotFoundError, BadRequestError

router = APIRouter(prefix="/api/experiment-plans", tags=["Experiment Runner"])

from app.graph import graph_manager

def get_runner_service(db: Database = Depends(get_mongo_db)) -> RunnerService:
    return RunnerService(db, graph_manager) 
    
@router.post("", response_model=ExperimentPlanResponse)
def create_experiment_plan(req: ExperimentPlanCreate, svc: RunnerService = Depends(get_runner_service)):
    try:
        return svc.create_plan(req)
    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{plan_id}", response_model=ExperimentPlanResponse)
def get_experiment_plan(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    try:
        return svc.get_plan(plan_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{plan_id}/run")
def run_experiment_plan(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    try:
        svc.get_plan(plan_id)
        svc.run_plan_async(plan_id)
        return {"status": "STARTING", "plan_id": plan_id}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{plan_id}/cancel")
def cancel_experiment_plan(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    try:
        svc.cancel_plan(plan_id)
        return {"status": "CANCEL_REQUESTED", "plan_id": plan_id}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{plan_id}/results")
def get_experiment_plan_results(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    try:
        return svc.get_plan_results(plan_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{plan_id}/export/json")
def export_results_json(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    """Export batch results as a JSON file download."""
    try:
        data = svc.get_plan_results(plan_id)
        content = json.dumps(data, default=str, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=experiment_{plan_id}_results.json"}
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{plan_id}/export/csv")
def export_results_csv(plan_id: str, svc: RunnerService = Depends(get_runner_service)):
    """Export batch results as a CSV file download."""
    try:
        data = svc.get_plan_results(plan_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "plan_id", "run_id", "experiment_id", "sweep_parameter", "sweep_value",
            "repetition", "status",
            "resilience_score", "impact_score", "recovery_time_seconds",
            "connectivity_preservation", "recovery_effectiveness"
        ])
        for r in data.get("results", []):
            scenario = r.get("scenario", {})
            analytics = r.get("analytics", {})
            writer.writerow([
                data["plan_id"],
                r.get("run_id", ""),
                r.get("experiment_id", ""),
                scenario.get("sweep_parameter", ""),
                scenario.get("sweep_value", ""),
                scenario.get("repetition", ""),
                "COMPLETED",
                analytics.get("resilience_score", ""),
                analytics.get("impact_score", ""),
                analytics.get("recovery_time_seconds", ""),
                analytics.get("connectivity_preservation", ""),
                analytics.get("recovery_effectiveness", ""),
            ])
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=experiment_{plan_id}_results.csv"}
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
