from enum import Enum

from pydantic import BaseModel, Field

from app.enums import ElementStatus, NodeType


class TopologyNode(BaseModel):
    id: str
    name: str
    type: NodeType
    status: ElementStatus


class TopologyLink(BaseModel):
    id: str
    source: str
    destination: str
    bandwidth: float = Field(description="Mbps")
    latency: float = Field(description="Milliseconds")
    packet_loss: float = Field(description="Percent")
    status: ElementStatus


class TopologySummary(BaseModel):
    nodes: int
    links: int
    active_nodes: int
    active_links: int


class TopologyResponse(BaseModel):
    """Complete topology of a network, read from the in-memory NetworkX graph."""
    network_id: str
    name: str
    nodes: list[TopologyNode]
    links: list[TopologyLink]
    summary: TopologySummary


class TemplateName(str, Enum):
    LINEAR = "linear"
    STAR = "star"
    RING = "ring"
    MESH = "mesh"


class TemplateRequest(BaseModel):
    node_count: int | None = Field(
        default=None,
        description="Total nodes. Defaults: linear 4, star 5 (1 hub + 4 leaves), ring 4, mesh 4. "
        "Allowed: linear 2-50, star 3-50, ring 3-50, mesh 2-12.",
    )
    bandwidth: float = Field(default=100, gt=0, description="Mbps for every generated link")
    latency: float = Field(default=10, ge=0, description="Milliseconds for every generated link")
