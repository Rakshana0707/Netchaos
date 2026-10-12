from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.enums import ElementStatus, FailureSeverity, FailureType, NetworkStatus


class BaselineNodeBase(BaseModel):
    node_id: str
    status: str


class BaselineNodeResponse(BaselineNodeBase):
    pass


class BaselineLinkBase(BaseModel):
    link_id: str
    status: str
    bandwidth: float
    latency: float
    packet_loss: float


class BaselineLinkResponse(BaselineLinkBase):
    pass


class NetworkBaselineBase(BaseModel):
    network_id: str


class NetworkBaselineResponse(NetworkBaselineBase):
    id: str
    created_at: datetime
    is_active: bool
    nodes: List[BaselineNodeResponse] = []
    links: List[BaselineLinkResponse] = []

    class Config:
        from_attributes = True


class FailureRecordBase(BaseModel):
    failure_type: str
    target_type: str
    target_id: Optional[str] = None
    severity: str
    description: Optional[str] = None
    status: str = "active"


class FailureRecordResponse(FailureRecordBase):
    id: str
    network_id: str
    detection_id: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FailureDetectionBase(BaseModel):
    network_id: str
    overall_status: str
    failed_nodes: int = 0
    failed_links: int = 0
    degraded_links: int = 0
    connected_components: int = 1
    affected_simulations: int = 0
    unreachable_pairs: int = 0


class FailureDetectionResponse(FailureDetectionBase):
    id: str
    baseline_id: Optional[str] = None
    detected_at: datetime
    failures: List[FailureRecordResponse] = []

    class Config:
        from_attributes = True


class ConnectivityCheckResponse(BaseModel):
    source: str
    destination: str
    reachable: bool
    reason: Optional[str] = None


class AffectedSimulationResponse(BaseModel):
    simulation_id: str
    source: str
    destination: str
    original_route: List[str]
    impact: str
    reason: Optional[str] = None

class AffectedTrafficReport(BaseModel):
    affected_simulations: List[AffectedSimulationResponse]
