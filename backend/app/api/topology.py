"""REST endpoints for the topology module using MongoDB."""
from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from pymongo.database import Database

from app.database.database import get_mongo_db
from app.graph import graph_manager
from app.schemas.link import LinkCreate, LinkResponse
from app.schemas.network import ErrorResponse, NetworkCreate, NetworkResponse
from app.schemas.node import NodeCreate, NodeResponse
from app.schemas.topology import TemplateName, TemplateRequest, TopologyResponse
from app.services.topology_service import TopologyService

router = APIRouter(
    prefix="/api/networks",
    tags=["topology"],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        404: {"model": ErrorResponse, "description": "Network, node or link not found"},
        409: {"model": ErrorResponse, "description": "Duplicate resource"},
    },
)

def get_service(db: Database = Depends(get_mongo_db)) -> TopologyService:
    return TopologyService(db, graph_manager)

def map_network(n: dict) -> NetworkResponse:
    return NetworkResponse(network_id=n["id"], name=n["name"], created_at=n["created_at"])

def map_node(n: dict) -> NodeResponse:
    return NodeResponse(
        node_id=n["id"], network_id=n["network_id"], name=n["name"],
        type=n["type"], status=n["status"], created_at=n["created_at"]
    )

def map_link(l: dict) -> LinkResponse:
    return LinkResponse(
        link_id=l["id"], network_id=l["network_id"], source=l["source_node_id"],
        destination=l["destination_node_id"], bandwidth=l["bandwidth"], latency=l["latency"],
        packet_loss=l["packet_loss"], status=l["status"], created_at=l["created_at"]
    )

# --- networks ---------------------------------------------------------------
@router.post("", response_model=NetworkResponse, status_code=status.HTTP_201_CREATED, summary="Create a network")
def create_network(data: NetworkCreate, service: TopologyService = Depends(get_service)):
    return map_network(service.create_network(data))

@router.get("", response_model=list[NetworkResponse], summary="List networks")
def list_networks(service: TopologyService = Depends(get_service)):
    return [map_network(n) for n in service.list_networks()]

@router.get("/{network_id}", response_model=NetworkResponse, summary="Get a network")
def get_network(network_id: str, service: TopologyService = Depends(get_service)):
    return map_network(service.get_network(network_id))

# --- nodes ------------------------------------------------------------------
@router.post("/{network_id}/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED, summary="Add a node")
def add_node(network_id: str, data: NodeCreate, service: TopologyService = Depends(get_service)):
    return map_node(service.add_node(network_id, data))

@router.get("/{network_id}/nodes", response_model=list[NodeResponse], summary="List nodes")
def list_nodes(network_id: str, service: TopologyService = Depends(get_service)):
    return [map_node(n) for n in service.list_nodes(network_id)]

@router.get("/{network_id}/nodes/{node_id}", response_model=NodeResponse, summary="Get a node")
def get_node(network_id: str, node_id: str, service: TopologyService = Depends(get_service)):
    return map_node(service.get_node(network_id, node_id))

@router.delete("/{network_id}/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a node")
def delete_node(network_id: str, node_id: str, service: TopologyService = Depends(get_service)):
    service.delete_node(network_id, node_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- links ------------------------------------------------------------------
@router.post("/{network_id}/links", response_model=LinkResponse, status_code=status.HTTP_201_CREATED, summary="Add a link")
def add_link(network_id: str, data: LinkCreate, service: TopologyService = Depends(get_service)):
    return map_link(service.add_link(network_id, data))

@router.get("/{network_id}/links", response_model=list[LinkResponse], summary="List links")
def list_links(network_id: str, service: TopologyService = Depends(get_service)):
    return [map_link(l) for l in service.list_links(network_id)]

@router.get("/{network_id}/links/{link_id}", response_model=LinkResponse, summary="Get a link")
def get_link(network_id: str, link_id: str, service: TopologyService = Depends(get_service)):
    return map_link(service.get_link(network_id, link_id))

@router.delete("/{network_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a link")
def delete_link(network_id: str, link_id: str, service: TopologyService = Depends(get_service)):
    service.delete_link(network_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- templates and topology ---------------------------------------------------
@router.post("/{network_id}/templates/{template_name}", response_model=TopologyResponse, status_code=status.HTTP_201_CREATED, summary="Apply template")
def apply_template(network_id: str, template_name: TemplateName, request: TemplateRequest | None = None, service: TopologyService = Depends(get_service)):
    return service.apply_template(network_id, template_name, request or TemplateRequest())

@router.get("/{network_id}/topology", response_model=TopologyResponse, summary="Complete topology")
def get_topology(network_id: str, service: TopologyService = Depends(get_service)):
    return service.get_topology(network_id)
