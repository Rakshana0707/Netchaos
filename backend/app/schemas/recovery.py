from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RecoveryStrategy(str, Enum):
    SHORTEST_HOP = "shortest_hop"
    LOWEST_LATENCY = "lowest_latency"
    HIGHEST_BANDWIDTH = "highest_bandwidth"
    COMPOSITE = "composite"


class RecoveryStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    RECOVERED = "RECOVERED"
    UNRECOVERABLE = "UNRECOVERABLE"
    NO_ALTERNATE_ROUTE = "NO_ALTERNATE_ROUTE"
    NOT_REQUIRED = "NOT_REQUIRED"
    FAILED = "FAILED"


class RecoveryRequest(BaseModel):
    simulation_id: str
    strategy: RecoveryStrategy = RecoveryStrategy.LOWEST_LATENCY
    latency_weight: float = 1.0
    hop_weight: float = 2.0
    bandwidth_weight: float = 0.5


class RecoveryResponse(BaseModel):
    recovery_id: Optional[str] = None
    network_id: str
    simulation_id: str

    status: RecoveryStatus

    failure_type: Optional[str] = None
    failure_description: Optional[str] = None

    original_route: Optional[List[str]] = None
    recovered_route: Optional[List[str]] = None

    route_changed: bool = False

    original_latency: Optional[float] = None
    recovered_latency: Optional[float] = None

    original_hop_count: Optional[int] = None
    recovered_hop_count: Optional[int] = None

    original_bandwidth: Optional[float] = None
    recovered_bandwidth: Optional[float] = None

    recovery_duration: Optional[float] = None
    connectivity_restored: bool = False

    class Config:
        from_attributes = True


class RoutePreviewRequest(BaseModel):
    simulation_id: str
    strategy: RecoveryStrategy = RecoveryStrategy.LOWEST_LATENCY
    latency_weight: float = 1.0
    hop_weight: float = 2.0
    bandwidth_weight: float = 0.5


class SimulationRouteResponse(BaseModel):
    simulation_id: str
    route: Optional[List[str]] = None
    route_status: str
