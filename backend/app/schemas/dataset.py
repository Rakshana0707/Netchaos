from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class DatasetFilter(BaseModel):
    failure_types: Optional[List[str]] = None
    topologies: Optional[List[str]] = None
    recovery_outcomes: Optional[List[str]] = None
    require_runner_only: Optional[bool] = False

class DatasetRecord(BaseModel):
    # Identification
    dataset_version: str
    experiment_id: str
    run_id: Optional[str] = None
    plan_id: Optional[str] = None
    network_id: str
    
    # Topology
    topology_type: str = "unknown"
    node_count: int = 0
    link_count: int = 0
    
    # Traffic Features
    source_node: Optional[str] = None
    destination_node: Optional[str] = None
    packet_count: Optional[int] = None
    packet_size: Optional[int] = None
    delivered_packets: Optional[int] = None
    dropped_packets: Optional[int] = None
    packet_loss_percentage: Optional[float] = None
    baseline_latency: Optional[float] = None
    chaos_latency: Optional[float] = None
    recovered_latency: Optional[float] = None
    baseline_throughput: Optional[float] = None
    chaos_throughput: Optional[float] = None
    recovered_throughput: Optional[float] = None
    
    # Chaos Features
    chaos_type: Optional[str] = None
    chaos_target: Optional[str] = None
    chaos_severity: Optional[str] = None
    packet_loss_injected: Optional[float] = None
    latency_injected: Optional[float] = None
    bandwidth_reduction: Optional[float] = None
    multiple_failure_count: int = 0
    
    # Failure Detection Features
    failure_detected: bool = False
    failed_node_count: int = 0
    failed_link_count: int = 0
    degraded_link_count: int = 0
    affected_traffic_count: int = 0
    partition_count: int = 0
    connectivity_before: Optional[int] = None
    connectivity_after_failure: Optional[int] = None
    failure_severity: Optional[str] = None
    
    # Recovery Features
    recovery_attempted: bool = False
    recovery_outcome: str = "NOT_ATTEMPTED"
    original_route_length: Optional[int] = None
    recovered_route_length: Optional[int] = None
    route_changed: Optional[bool] = None
    recovery_time: Optional[float] = None
    
    # Resilience/Performance Features (from Analytics)
    latency_degradation_percentage: Optional[float] = None
    packet_loss_degradation_percentage: Optional[float] = None
    throughput_degradation_percentage: Optional[float] = None
    connectivity_preservation: Optional[float] = None
    performance_preservation: Optional[float] = None
    recovery_effectiveness: Optional[float] = None
    impact_score: Optional[float] = None
    resilience_score: Optional[float] = None
    
    # Data Quality
    data_quality: str = "VALID" # VALID, PARTIAL, INVALID
    validation_warnings: List[str] = Field(default_factory=list)

class DatasetManifest(BaseModel):
    id: str = Field(alias="dataset_id")
    name: str
    description: Optional[str] = None
    version: str
    schema_version: str = "1.0"
    generator_version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    record_count: int = 0
    source_experiments: List[str] = Field(default_factory=list)
    filters: Optional[DatasetFilter] = None
    
    model_config = ConfigDict(populate_by_name=True)

class DatasetResponse(BaseModel):
    dataset_id: str
    metadata: DatasetManifest
    records: List[DatasetRecord]

class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    version: str = "1.0"
    filters: Optional[DatasetFilter] = None
    
class DatasetStatistics(BaseModel):
    total_records: int
    data_quality_report: Dict[str, Any]
    failure_distribution: Dict[str, Any]
    recovery_distribution: Dict[str, Any]
    metrics: Dict[str, Any] # Mean, Median, Min, Max of scores
