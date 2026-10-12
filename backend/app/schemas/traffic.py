from datetime import datetime

from pydantic import BaseModel, Field

from app.config import MAX_PACKET_COUNT, MAX_PACKET_SIZE
from app.enums import PacketStatus, SimulationStatus


class SimulationCreate(BaseModel):
    source: str = Field(description="node_id the packets start from", examples=["node_001"])
    destination: str = Field(description="node_id the packets are sent to", examples=["node_006"])
    packet_count: int = Field(gt=0, le=MAX_PACKET_COUNT, description="Number of packets to send", examples=[100])
    packet_size: int = Field(gt=0, le=MAX_PACKET_SIZE, description="Size of every packet in bytes", examples=[1024])
    random_seed: int | None = Field(
        default=None, ge=0, le=2**32 - 1,
        description="Seed for packet-loss decisions. Omit it and one is generated and stored, "
        "so the run can still be reproduced.",
        examples=[42],
    )
    store_packets: bool = Field(
        default=False,
        description="Also save one database row per packet (only allowed for small simulations).",
    )
    recovery_id: str | None = Field(
        default=None,
        description="Post-recovery traffic: id of a RECOVERED recovery event (e.g. rec_001_001). The packets "
        "are sent along exactly that recovered route; failed nodes and links are still never used.",
        examples=["rec_001_001"],
    )


class SimulationResponse(BaseModel):
    simulation_id: str = Field(examples=["sim_001"])
    network_id: str
    source: str
    destination: str
    packet_count: int
    packet_size: int
    random_seed: int
    store_packets: bool
    status: SimulationStatus
    phase: str | None = Field(default=None, description="baseline | chaos | post_recovery, when part of a lifecycle")
    recovery_id: str | None = Field(default=None, description="Recovery event this (post-recovery) run followed")
    experiment_id: str | None = Field(default=None, description="Experiment this run belongs to, if any")
    failure_reason: str | None = None
    route_available: bool | None = None
    route: list[str] | None = None
    delivered_packets: int | None = None
    dropped_packets: int | None = None
    packet_loss_percentage: float | None = None
    path_latency_ms: float | None = None
    hop_count: int | None = None
    path_bandwidth_mbps: float | None = None
    throughput_mbps: float | None = None
    simulated_duration_ms: float | None = Field(default=None, description="Simulated (model) time")
    execution_duration_ms: float | None = Field(default=None, description="Real time the run took")
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None



class MetricsResponse(BaseModel):
    """Metrics of a finished simulation. For a failed one, route_available is false and metrics are null."""
    simulation_id: str
    network_id: str
    source: str
    destination: str
    status: SimulationStatus
    failure_reason: str | None = None
    route_available: bool | None = None
    route: list[str] | None = None
    packet_count: int
    packet_size: int
    random_seed: int
    delivered_packets: int | None = None
    dropped_packets: int | None = None
    packet_loss_percentage: float | None = None
    total_data_transferred_bytes: int | None = Field(default=None, description="delivered_packets * packet_size")
    path_latency_ms: float | None = None
    hop_count: int | None = None
    path_bandwidth_mbps: float | None = None
    throughput_mbps: float | None = None
    simulated_duration_ms: float | None = Field(default=None, description="Simulated (model) time")
    execution_duration_ms: float | None = Field(default=None, description="Real time the run took")



class PacketResponse(BaseModel):
    packet_id: str = Field(examples=["pkt_001"])
    simulation_id: str
    sequence_number: int
    source: str
    destination: str
    packet_size: int
    status: PacketStatus
    route: list[str]
    dropped_at_link_id: str | None = None
    completed_at_ms: float = Field(description="Simulated time the packet was delivered or dropped")
    created_at: datetime



class PacketPage(BaseModel):
    total: int = Field(description="Packets stored for this simulation (0 unless store_packets was set)")
    limit: int
    offset: int
    packets: list[PacketResponse]
