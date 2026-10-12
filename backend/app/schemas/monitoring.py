from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"

class NodeMetrics(BaseModel):
    total: int
    active: int
    failed: int

class LinkMetrics(BaseModel):
    total: int
    active: int
    failed: int
    degraded: int

class TrafficMetricsSummary(BaseModel):
    active_flows: int
    affected_flows: int
    total_packets: int
    delivered_packets: int
    dropped_packets: int
    packet_loss_percentage: float
    average_latency: float
    throughput: float

class ConnectivityMetrics(BaseModel):
    partitions: int
    traffic_availability: float

class MonitoringSnapshot(BaseModel):
    id: str | None = None
    network_id: str
    timestamp: datetime
    health_status: HealthStatus
    nodes: NodeMetrics
    links: LinkMetrics
    traffic: TrafficMetricsSummary
    connectivity: ConnectivityMetrics

class SingleLinkMetrics(BaseModel):
    link_id: str
    source: str
    destination: str
    status: str
    bandwidth: float
    latency: float
    packet_loss: float
    baseline_bandwidth: Optional[float]
    baseline_latency: Optional[float]
    baseline_packet_loss: Optional[float]
    bandwidth_change_percent: Optional[float]
    latency_change_percent: Optional[float]
    packet_loss_change: Optional[float]
    health_status: HealthStatus

class SingleNodeMetrics(BaseModel):
    node_id: str
    status: str
    connected_links: int
    failed_links: int
    affected_traffic_count: int
    health_status: HealthStatus

class RecoverySummary(BaseModel):
    total_recovery_events: int
    successful_recoveries: int
    failed_recoveries: int
    average_recovery_time: float
    minimum_recovery_time: Optional[float]
    maximum_recovery_time: Optional[float]
    connectivity_restored_percentage: float

class ChaosPhaseMetrics(BaseModel):
    latency: float
    packet_loss: float
    throughput: float
    availability: float
    hop_count: float

class ChaosImpactComparison(BaseModel):
    baseline: ChaosPhaseMetrics
    chaos: ChaosPhaseMetrics
    recovery: ChaosPhaseMetrics

class AffectedFlow(BaseModel):
    simulation_id: str
    source: str
    destination: str
    original_route: List[str]
    current_route: List[str]
    status: str
    latency_change: float
    bandwidth_change: float
    route_changed: bool

class PartitionInfo(BaseModel):
    partition_count: int
    partitions: List[List[str]]

class MonitoringConfig(BaseModel):
    packet_loss_warning: float = 5.0
    packet_loss_critical: float = 15.0
    latency_warning_percent: float = 20.0
    latency_critical_percent: float = 50.0
    throughput_warning_percent: float = 20.0
