from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExperimentCreate(BaseModel):
    name: str
    description: str


class MetricComparison(BaseModel):
    """One metric across the lifecycle: baseline, worst (chaos phase), recovered (post-recovery), final.

    Anything that is undefined (e.g. latency while the flow was down) is None, never a made-up 0.
    """
    baseline: Optional[float] = None
    worst: Optional[float] = None
    recovered: Optional[float] = None
    final: Optional[float] = None
    degradation_absolute: Optional[float] = None
    degradation_percentage: Optional[float] = None
    recovery_improvement_absolute: Optional[float] = None
    recovery_improvement_percentage: Optional[float] = None
    recovery_effectiveness: Optional[float] = None  # 0-100%


class PerformanceAnalysis(BaseModel):
    latency: MetricComparison
    packet_loss: MetricComparison
    throughput: MetricComparison
    availability: MetricComparison


class EventDetail(BaseModel):
    timestamp: datetime
    event_type: str
    description: str
    source_module: str
    severity: str


class FailureImpact(BaseModel):
    failure_id: str
    failure_type: str
    affected_nodes: int
    affected_links: int
    affected_traffic: int
    partitions_created: int
    packet_loss_change: Optional[float] = None
    latency_change_percent: Optional[float] = None  # None when the flow was down (latency undefined)
    throughput_change_percent: Optional[float] = None
    availability_change: Optional[float] = None
    impact_score: Optional[float] = None


class RouteSummary(BaseModel):
    original_route: List[str]
    recovered_route: List[str]
    route_changed: bool
    hop_difference: Optional[int] = None
    latency_difference: Optional[float] = None
    bandwidth_difference: Optional[float] = None


class RecoveryAnalysis(BaseModel):
    total_events: int
    successful: int
    failed: int
    routes: List[RouteSummary]


class ExperimentResponse(BaseModel):
    id: str
    network_id: str
    name: str
    description: str
    status: ExperimentStatus
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    baseline_snapshot_id: Optional[str]
    final_snapshot_id: Optional[str]
    phases: Optional[Dict[str, Any]] = None  # explicit ids of the records that make up this experiment
    created_at: datetime


class ExperimentDetailResponse(BaseModel):
    experiment: ExperimentResponse
    timeline: List[EventDetail]
    performance_analysis: Optional[PerformanceAnalysis]
    failure_impacts: List[FailureImpact]
    recovery_analysis: Optional[RecoveryAnalysis]
    metrics: Optional[Dict[str, Any]] = None  # lifecycle phase metrics (see analysis/phase_metrics.py)


class PhaseLinks(BaseModel):
    """Explicit ids of the records that make up one experiment (all optional)."""
    baseline_simulation_id: Optional[str] = None
    chaos_simulation_id: Optional[str] = None
    post_recovery_simulation_id: Optional[str] = None
    recovery_id: Optional[str] = None
    detection_id: Optional[str] = None
    chaos_experiment_ids: Optional[List[str]] = None
