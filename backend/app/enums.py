"""Value sets shared by the database models, schemas and graph layer."""
from enum import Enum


class NodeType(str, Enum):
    ROUTER = "router"
    HOST = "host"
    SERVER = "server"
    CLIENT = "client"
    SWITCH = "switch"
    ENDPOINT = "endpoint"


class ElementStatus(str, Enum):
    """Status of a node or link. 'failed' is set (and reverted) only by the chaos module."""
    ACTIVE = "active"
    FAILED = "failed"


class SimulationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PacketStatus(str, Enum):
    CREATED = "created"
    TRANSMITTING = "transmitting"
    DELIVERED = "delivered"
    DROPPED = "dropped"


class ScenarioType(str, Enum):
    """Chaos scenarios. ``multi_failure`` is an experiment-level scenario: its child events use the others."""
    ROUTER_FAILURE = "router_failure"
    LINK_FAILURE = "link_failure"
    PACKET_LOSS = "packet_loss"
    LATENCY = "latency"
    BANDWIDTH_REDUCTION = "bandwidth_reduction"
    CONGESTION = "congestion"
    MULTI_FAILURE = "multi_failure"


class TargetType(str, Enum):
    NODE = "node"
    LINK = "link"
    NETWORK = "network"  # used for multi_failure experiments, which span several targets


class ChaosStatus(str, Enum):
    """Lifecycle of a chaos experiment/event.

    Applying is atomic, so ``pending`` and ``failed`` are reserved: no row is ever committed in those
    states today. Rows are ``active`` until reverted, then ``reverted``.
    """
    PENDING = "pending"
    ACTIVE = "active"
    REVERTED = "reverted"
    FAILED = "failed"


class FailureSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NetworkStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class FailureType(str, Enum):
    NODE_FAILURE = "node_failure"
    LINK_FAILURE = "link_failure"
    LINK_DEGRADATION = "link_degradation"
    NETWORK_PARTITION = "network_partition"
    ROUTE_UNAVAILABLE = "route_unavailable"
    ROUTE_DEGRADED = "route_degraded"
    UNREACHABLE_PAIR = "unreachable_pair"
