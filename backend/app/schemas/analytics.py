from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class AnalyticsSummaryResponse(BaseModel):
    network_id: str
    experiments_analyzed: int
    successful_recoveries: int
    failed_recoveries: int
    average_recovery_time: Optional[float] = None
    average_impact_score: Optional[float] = None
    average_connectivity_preservation: Optional[float] = None
    average_recovery_effectiveness: Optional[float] = None
    resilience_score: Optional[float] = None

class FailureRanking(BaseModel):
    rank: int
    experiment_id: str
    failure_type: str
    severity: str
    impact_score: float
    affected_nodes: int
    affected_links: int
    affected_traffic: int
    connectivity_preservation: Optional[float] = None
    latency_degradation: Optional[float] = None
    packet_loss_degradation: Optional[float] = None
    throughput_degradation: Optional[float] = None
    recovery_time: Optional[float] = None
    recoverable: bool

class RouteResilienceMetrics(BaseModel):
    original_hop_count: int
    recovered_hop_count: int
    hop_count_increase: int
    original_latency: float
    recovered_latency: float
    latency_increase: float
    original_bandwidth: float
    recovered_bandwidth: float
    bandwidth_reduction: float
    route_changed: bool

class ExperimentAnalytics(BaseModel):
    experiment_id: str
    failure_type: str
    impact_score: Optional[float] = None  # None when baseline or chaos-phase data is missing
    connectivity: Optional[float] = None
    latency_degradation: Optional[float] = None
    packet_loss_degradation: Optional[float] = None
    throughput_degradation: Optional[float] = None
    recovery_time: Optional[float] = None
    recovery_effectiveness: Optional[float] = None
    route_changed: bool
    recoverable: bool
    # Explicit metrics for baseline, chaos, recovery, final
    baseline_latency: Optional[float] = None
    chaos_latency: Optional[float] = None
    recovery_latency: Optional[float] = None
    baseline_throughput: Optional[float] = None
    chaos_throughput: Optional[float] = None
    recovery_throughput: Optional[float] = None
    baseline_packet_loss: Optional[float] = None
    chaos_packet_loss: Optional[float] = None
    recovery_packet_loss: Optional[float] = None
    # Lifecycle context
    recovery_status: str = "unknown"  # recovered | not_required | unrecoverable | not_attempted | unknown
    post_recovery_latency_degradation: Optional[float] = None
    data_complete: bool = False
    missing: List[str] = Field(default_factory=list)

class CompareRequest(BaseModel):
    experiment_ids: List[str]

class AnalyticsComparisonResponse(BaseModel):
    experiments: List[ExperimentAnalytics]
    summary_message: Optional[str] = None

class ResearchReport(BaseModel):
    experiment_id: str
    overview: str
    baseline: Dict[str, Any]
    failure: Dict[str, Any]
    impact: Dict[str, Any]
    recovery: Dict[str, Any]
    performance: Dict[str, Any]
    resilience_score: Optional[float] = None  # None when there is not enough data
    interpretation: str
    disclaimer: str = ""
    data_complete: bool = False
    missing: List[str] = Field(default_factory=list)
    route_analysis: Optional[RouteResilienceMetrics] = None
    research_findings: List[str]

class NetworkReport(BaseModel):
    network_id: str
    number_of_experiments: int
    failure_types_tested: List[str]
    most_severe_failure: Optional[str] = None
    least_severe_failure: Optional[str] = None
    average_resilience: Optional[float] = None
    successful_recovery_percentage: Optional[float] = None
    average_recovery_time: Optional[float] = None
    average_connectivity_preservation: Optional[float] = None
    
    # Statistical summary
    impact_score_stats: Optional[Dict[str, float]] = None
    recovery_time_stats: Optional[Dict[str, float]] = None
    warning_message: Optional[str] = None

class ExperimentConfigurationExport(BaseModel):
    experiment_id: str
    network_id: str
    network_topology: Dict[str, Any]
    traffic_configuration: List[Dict[str, Any]]
    chaos_configuration: Dict[str, Any]
    random_seed: Optional[int] = None
    parent_experiment_id: Optional[str] = None
