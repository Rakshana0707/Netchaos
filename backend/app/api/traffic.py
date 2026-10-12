"""REST endpoints for traffic using MongoDB."""
from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.graph import graph_manager
from app.schemas.network import ErrorResponse
from app.schemas.traffic import MetricsResponse, PacketPage, PacketResponse, SimulationCreate, SimulationResponse
from app.services.traffic_service import TrafficService

router = APIRouter(
    prefix="/api/networks/{network_id}/traffic/simulations",
    tags=["traffic"],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid simulation parameters"},
        404: {"model": ErrorResponse, "description": "Network, node or simulation not found"},
        409: {"model": ErrorResponse, "description": "Simulation already running / finished, or metrics not ready"},
    },
)

def get_service(db: Database = Depends(get_mongo_db)) -> TrafficService:
    return TrafficService(db, graph_manager)

def map_simulation(sim: dict) -> SimulationResponse:
    return SimulationResponse(
        simulation_id=sim["id"], network_id=sim["network_id"], source=sim["source_node_id"],
        destination=sim["destination_node_id"], packet_count=sim["packet_count"], packet_size=sim["packet_size"],
        random_seed=sim["random_seed"], store_packets=sim["store_packets"], status=sim["status"],
        phase=sim.get("phase"), recovery_id=sim.get("recovery_id"), experiment_id=sim.get("experiment_id"),
        failure_reason=sim.get("failure_reason"), route_available=sim.get("route_available"), route=sim.get("route"),
        delivered_packets=sim.get("delivered_packets"), dropped_packets=sim.get("dropped_packets"),
        packet_loss_percentage=sim.get("packet_loss_percentage"), path_latency_ms=sim.get("path_latency_ms"),
        hop_count=sim.get("hop_count"), path_bandwidth_mbps=sim.get("path_bandwidth_mbps"),
        throughput_mbps=sim.get("throughput_mbps"), simulated_duration_ms=sim.get("simulated_duration_ms"),
        execution_duration_ms=sim.get("execution_duration_ms"), created_at=sim["created_at"],
        started_at=sim.get("started_at"), completed_at=sim.get("completed_at"),
    )

def map_metrics(sim: dict) -> MetricsResponse:
    delivered = sim.get("delivered_packets")
    packet_size = sim["packet_size"]
    return MetricsResponse(
        simulation_id=sim["id"], network_id=sim["network_id"], source=sim["source_node_id"],
        destination=sim["destination_node_id"], status=sim["status"], failure_reason=sim.get("failure_reason"),
        route_available=sim.get("route_available"), route=sim.get("route"), packet_count=sim["packet_count"],
        packet_size=packet_size, random_seed=sim["random_seed"], delivered_packets=delivered,
        dropped_packets=sim.get("dropped_packets"), packet_loss_percentage=sim.get("packet_loss_percentage"),
        total_data_transferred_bytes=None if delivered is None else delivered * packet_size,
        path_latency_ms=sim.get("path_latency_ms"), hop_count=sim.get("hop_count"),
        path_bandwidth_mbps=sim.get("path_bandwidth_mbps"), throughput_mbps=sim.get("throughput_mbps"),
        simulated_duration_ms=sim.get("simulated_duration_ms"), execution_duration_ms=sim.get("execution_duration_ms"),
    )

def map_packet(p: dict) -> PacketResponse:
    return PacketResponse(
        packet_id=p["packet_id"], simulation_id=p["simulation_id"],
        sequence_number=p["sequence_number"], source=p["source_node_id"],
        destination=p["destination_node_id"], packet_size=p["packet_size"], status=p["status"],
        route=p["route"], dropped_at_link_id=p.get("dropped_at_link_id"),
        completed_at_ms=p["completed_at_ms"], created_at=p["created_at"],
    )

@router.post("", response_model=SimulationResponse, status_code=status.HTTP_201_CREATED, summary="Create a traffic simulation")
def create_simulation(network_id: str, data: SimulationCreate, service: TrafficService = Depends(get_service)):
    return map_simulation(service.create_simulation(network_id, data))

@router.get("", response_model=list[SimulationResponse], summary="Simulation history, newest first")
def list_simulations(network_id: str, service: TrafficService = Depends(get_service)):
    return [map_simulation(s) for s in service.list_simulations(network_id)]

@router.get("/{simulation_id}", response_model=SimulationResponse, summary="Get one simulation")
def get_simulation(network_id: str, simulation_id: str, service: TrafficService = Depends(get_service)):
    return map_simulation(service.get_simulation(network_id, simulation_id))

@router.post("/{simulation_id}/run", response_model=SimulationResponse, summary="Run a pending simulation")
def run_simulation(network_id: str, simulation_id: str, service: TrafficService = Depends(get_service)):
    return map_simulation(service.run_simulation(network_id, simulation_id))

@router.get("/{simulation_id}/metrics", response_model=MetricsResponse, summary="Metrics of a finished simulation")
def get_metrics(network_id: str, simulation_id: str, service: TrafficService = Depends(get_service)):
    return map_metrics(service.get_metrics(network_id, simulation_id))

@router.get("/{simulation_id}/packets", response_model=PacketPage, summary="Packet-level records")
def list_packets(network_id: str, simulation_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), service: TrafficService = Depends(get_service)):
    total, packets = service.list_packets(network_id, simulation_id, limit, offset)
    return PacketPage(total=total, limit=limit, offset=offset, packets=[map_packet(p) for p in packets])
