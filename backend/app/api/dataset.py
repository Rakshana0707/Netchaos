from fastapi import APIRouter, Depends, HTTPException, Response
from pymongo.database import Database
import csv
import io
import json

from app.database.database import get_mongo_db
from app.schemas.dataset import DatasetCreate, DatasetManifest, DatasetResponse, DatasetStatistics
from app.services.dataset_service import DatasetService
from app.errors import NotFoundError, BadRequestError

router = APIRouter(prefix="/api/datasets", tags=["Dataset Lab"])

from app.graph import graph_manager

def get_dataset_service(db: Database = Depends(get_mongo_db)) -> DatasetService:
    return DatasetService(db, graph_manager)

@router.post("", response_model=DatasetManifest)
def create_dataset(req: DatasetCreate, svc: DatasetService = Depends(get_dataset_service)):
    try:
        return svc.create_dataset(req)
    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("")
def get_datasets(svc: DatasetService = Depends(get_dataset_service)):
    return svc.get_datasets()

@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, svc: DatasetService = Depends(get_dataset_service)):
    try:
        return svc.get_dataset(dataset_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{dataset_id}/statistics", response_model=DatasetStatistics)
def get_dataset_statistics(dataset_id: str, svc: DatasetService = Depends(get_dataset_service)):
    try:
        return svc.get_dataset_statistics(dataset_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{dataset_id}/export/json")
def export_dataset_json(dataset_id: str, svc: DatasetService = Depends(get_dataset_service)):
    try:
        ds = svc.get_dataset(dataset_id)
        content = json.dumps(ds.model_dump(), default=str, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={dataset_id}_dataset.json"}
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{dataset_id}/export/csv")
def export_dataset_csv(dataset_id: str, svc: DatasetService = Depends(get_dataset_service)):
    try:
        ds = svc.get_dataset(dataset_id)
        if not ds.records:
            return Response(content="No records", media_type="text/csv")
            
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write Header
        headers = list(ds.records[0].model_dump().keys())
        writer.writerow(headers)
        
        # Write Rows
        for rec in ds.records:
            row_dict = rec.model_dump()
            row = [row_dict.get(h, "") for h in headers]
            writer.writerow(row)
            
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={dataset_id}_dataset.csv"}
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
