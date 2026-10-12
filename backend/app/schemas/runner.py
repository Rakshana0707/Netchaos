from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class ParameterSweep(BaseModel):
    parameter: str
    values: List[Any]

class TrafficConfiguration(BaseModel):
    source: str
    destination: str
    packet_count: int
    packet_size: int
    protocol: str = "TCP"

class ChaosConfiguration(BaseModel):
    type: str # link_failure, router_failure, ...
    target: str # e.g. Node A, or link_id
    parameters: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow")

class RecoveryConfiguration(BaseModel):
    enabled: bool = True
    strategy: str = "shortest_hop"

class ExperimentPlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    network_id: str
    traffic: TrafficConfiguration
    chaos: ChaosConfiguration
    recovery: RecoveryConfiguration
    repetitions: int = 1
    random_seed: Optional[int] = None
    sweep: Optional[ParameterSweep] = None

class ExperimentRunStatus(BaseModel):
    run_id: str
    experiment_id: Optional[str] = None  # Maps to HistoryService experiment
    run_number: int
    status: str # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    configuration: Dict[str, Any]

class ExperimentPlanResponse(BaseModel):
    plan_id: str
    name: str
    network_id: str
    status: str # CREATED, RUNNING, COMPLETED, PARTIAL, FAILED, CANCELLED
    total_runs: int
    completed_runs: int
    failed_runs: int
    cancelled_runs: int
    progress_percentage: float
    runs: List[ExperimentRunStatus]
    created_at: datetime
