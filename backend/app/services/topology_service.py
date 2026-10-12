"""Business logic for topologies using MongoDB."""
import networkx as nx
from datetime import datetime, timezone
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.enums import ElementStatus
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.graph import GraphManager
from app.schemas.link import LinkCreate
from app.schemas.network import NetworkCreate
from app.schemas.node import NodeCreate
from app.schemas.topology import (
    TemplateName, TemplateRequest, TopologyLink, TopologyNode, TopologyResponse, TopologySummary,
)
from app.services.templates import SPECS, build_template


class TopologyService:
    def __init__(self, db: Database, graphs: GraphManager) -> None:
        self.db = db
        self.graphs = graphs

    def _now(self):
        return datetime.now(timezone.utc)

    # --- networks --------------------------------------------------------
    def create_network(self, data: NetworkCreate) -> dict:
        highest = self.db.networks.find_one({}, sort=[("id", -1)])
        highest_id = 0
        if highest and highest["id"].startswith("net_"):
            highest_id = int(highest["id"].split("_")[1]) if len(highest["id"].split("_")) > 1 and highest["id"].split("_")[1].isdigit() else 0
            
        net_id = f"net_{highest_id + 1:03d}"
        network = {
            "id": net_id,
            "name": data.name,
            "created_at": self._now(),
            "next_node_seq": 1,
            "next_link_seq": 1
        }
        try:
            self.db.networks.insert_one(network)
        except DuplicateKeyError:
            raise ConflictError("Another network was created at the same moment; please retry")
            
        self.graphs.create_graph(net_id)
        return network

    def list_networks(self) -> list[dict]:
        return list(self.db.networks.find({}, {"_id": 0}).sort("id", 1))

    def get_network(self, network_id: str, lock: bool = False) -> dict:
        # MongoDB does not lock on read like MySQL's with_for_update.
        # We rely on unique indexes for constraints.
        network = self.db.networks.find_one({"id": network_id}, {"_id": 0})
        if not network:
            raise NotFoundError(f"Network '{network_id}' not found", "network_not_found")
        return network

    # --- nodes -----------------------------------------------------------
    def add_node(self, network_id: str, data: NodeCreate) -> dict:
        network = self.get_network(network_id)
        self._ensure_graph(network_id)
        
        taken = self.db.nodes.find_one({"network_id": network_id, "name": data.name})
        if taken:
            raise ConflictError(f"A node named '{data.name}' already exists in network '{network_id}'", "duplicate_node")

        node_id = f"node_{network['next_node_seq']:03d}"
        
        node = {
            "id": node_id,
            "network_id": network_id,
            "name": data.name,
            "type": data.type.value,
            "status": ElementStatus.ACTIVE.value,
            "created_at": self._now()
        }
        
        try:
            self.db.nodes.insert_one(node)
            self.db.networks.update_one({"id": network_id}, {"$inc": {"next_node_seq": 1}})
        except DuplicateKeyError:
            raise ConflictError("The change conflicts with existing data")

        self.graphs.add_node(
            network_id, node_id, name=node["name"], type=node["type"], 
            status=node["status"], created_at=node["created_at"].isoformat()
        )
        return node

    def list_nodes(self, network_id: str) -> list[dict]:
        self.get_network(network_id)
        return list(self.db.nodes.find({"network_id": network_id}, {"_id": 0}).sort("id", 1))

    def get_node(self, network_id: str, node_id: str) -> dict:
        self.get_network(network_id)
        node = self.db.nodes.find_one({"id": node_id, "network_id": network_id}, {"_id": 0})
        if not node:
            raise NotFoundError(f"Node '{node_id}' not found in network '{network_id}'", "node_not_found")
        return node

    def delete_node(self, network_id: str, node_id: str) -> None:
        self.get_network(network_id)
        self._ensure_graph(network_id)
        node = self.get_node(network_id, node_id)
        
        self.db.links.delete_many({
            "network_id": network_id,
            "$or": [{"source_node_id": node_id}, {"destination_node_id": node_id}]
        })
        self.db.nodes.delete_one({"id": node_id, "network_id": network_id})
        
        self.graphs.remove_node(network_id, node_id)

    # --- links -----------------------------------------------------------
    def add_link(self, network_id: str, data: LinkCreate) -> dict:
        network = self.get_network(network_id)
        self._ensure_graph(network_id)
        
        for role, node_id in (("Source", data.source), ("Destination", data.destination)):
            if not self.db.nodes.find_one({"id": node_id, "network_id": network_id}):
                raise NotFoundError(f"{role} node '{node_id}' not found in network '{network_id}'", "node_not_found")
                
        if data.source == data.destination:
            raise BadRequestError("A link cannot connect a node to itself", "invalid_link")
            
        existing_link = self.db.links.find_one({
            "network_id": network_id,
            "$or": [
                {"source_node_id": data.source, "destination_node_id": data.destination},
                {"source_node_id": data.destination, "destination_node_id": data.source},
            ]
        })
        if existing_link:
            raise ConflictError(f"Nodes '{data.source}' and '{data.destination}' are already linked", "duplicate_link")

        link_id = f"link_{network['next_link_seq']:03d}"
        link = {
            "id": link_id,
            "network_id": network_id,
            "source_node_id": data.source,
            "destination_node_id": data.destination,
            "bandwidth": data.bandwidth,
            "latency": data.latency,
            "packet_loss": data.packet_loss,
            "status": ElementStatus.ACTIVE.value,
            "created_at": self._now()
        }
        try:
            self.db.links.insert_one(link)
            self.db.networks.update_one({"id": network_id}, {"$inc": {"next_link_seq": 1}})
        except DuplicateKeyError:
            raise ConflictError("The change conflicts with existing data")

        self.graphs.add_link(
            network_id, link["id"], link["source_node_id"], link["destination_node_id"],
            bandwidth=link["bandwidth"], latency=link["latency"], packet_loss=link["packet_loss"], status=link["status"]
        )
        return link

    def list_links(self, network_id: str) -> list[dict]:
        self.get_network(network_id)
        return list(self.db.links.find({"network_id": network_id}, {"_id": 0}).sort("id", 1))

    def get_link(self, network_id: str, link_id: str) -> dict:
        self.get_network(network_id)
        link = self.db.links.find_one({"id": link_id, "network_id": network_id}, {"_id": 0})
        if not link:
            raise NotFoundError(f"Link '{link_id}' not found in network '{network_id}'", "link_not_found")
        return link

    def delete_link(self, network_id: str, link_id: str) -> None:
        self.get_network(network_id)
        self._ensure_graph(network_id)
        link = self.get_link(network_id, link_id)
        self.db.links.delete_one({"id": link_id, "network_id": network_id})
        self.graphs.remove_link(network_id, link_id)

    # --- templates -------------------------------------------------------
    def apply_template(self, network_id: str, template: TemplateName, request: TemplateRequest) -> TopologyResponse:
        network = self.get_network(network_id)
        spec = SPECS[template]
        count = request.node_count if request.node_count is not None else spec.default_count
        if not spec.min_count <= count <= spec.max_count:
            raise BadRequestError(
                f"node_count for '{template.value}' must be between {spec.min_count} and {spec.max_count}",
                "invalid_node_count",
            )
            
        if self.db.nodes.count_documents({"network_id": network_id}) > 0:
            raise ConflictError(
                f"Network '{network_id}' already has nodes; templates can only be applied to an empty network",
                "network_not_empty",
            )

        # Load the in-memory graph BEFORE any database write: after a restart it may not exist yet, and a
        # failure after the inserts would leave the database and the graph out of step.
        self._ensure_graph(network_id)
        node_specs, link_specs = build_template(template, count)
        
        nodes, links = [], []
        node_seq = network["next_node_seq"]
        for name, node_type in node_specs:
            nodes.append({
                "id": f"node_{node_seq:03d}", "network_id": network_id, "name": name,
                "type": node_type.value, "status": ElementStatus.ACTIVE.value, "created_at": self._now()
            })
            node_seq += 1
            
        if nodes:
            self.db.nodes.insert_many(nodes)
            
        link_seq = network["next_link_seq"]
        for a, b in link_specs:
            links.append({
                "id": f"link_{link_seq:03d}", "network_id": network_id, "source_node_id": nodes[a]["id"],
                "destination_node_id": nodes[b]["id"], "bandwidth": request.bandwidth, 
                "latency": request.latency, "packet_loss": 0, "status": ElementStatus.ACTIVE.value,
                "created_at": self._now()
            })
            link_seq += 1
            
        if links:
            self.db.links.insert_many(links)
            
        self.db.networks.update_one({"id": network_id}, {"$set": {"next_node_seq": node_seq, "next_link_seq": link_seq}})

        for node in nodes:
            self.graphs.add_node(
                network_id, node["id"], name=node["name"], type=node["type"], 
                status=node["status"], created_at=node["created_at"].isoformat()
            )
        for link in links:
            self.graphs.add_link(
                network_id, link["id"], link["source_node_id"], link["destination_node_id"],
                bandwidth=link["bandwidth"], latency=link["latency"], packet_loss=link["packet_loss"], status=link["status"]
            )
        return self.get_topology(network_id)

    # --- topology --------------------------------------------------------
    def get_topology(self, network_id: str) -> TopologyResponse:
        network = self.get_network(network_id)
        self._ensure_graph(network_id)
        nodes = sorted(self.graphs.get_nodes(network_id), key=lambda n: n["node_id"])
        links = sorted(self.graphs.get_links(network_id), key=lambda l: l["link_id"])
        
        topo_nodes = [
            TopologyNode(id=n["node_id"], name=n["name"], type=n["type"], status=n["status"]) for n in nodes
        ]
        topo_links = [
            TopologyLink(
                id=l["link_id"], source=l["source"], destination=l["destination"], bandwidth=l["bandwidth"],
                latency=l["latency"], packet_loss=l["packet_loss"], status=l["status"],
            )
            for l in links
        ]
        active = ElementStatus.ACTIVE
        return TopologyResponse(
            network_id=network["id"],
            name=network["name"],
            nodes=topo_nodes,
            links=topo_links,
            summary=TopologySummary(
                nodes=len(topo_nodes),
                links=len(topo_links),
                active_nodes=sum(n.status == active for n in topo_nodes),
                active_links=sum(l.status == active for l in topo_links),
            ),
        )

    def snapshot_graph(self, network_id: str) -> nx.Graph:
        self.get_network(network_id)
        self._ensure_graph(network_id)
        return self.graphs.snapshot(network_id)

    def lock_network(self, network_id: str) -> dict:
        network = self.get_network(network_id, lock=True)
        self._ensure_graph(network_id)
        return network

    def reload_graph(self, network_id: str) -> None:
        self.graphs.drop_graph(network_id)
        self._ensure_graph(network_id)

    def _ensure_graph(self, network_id: str) -> None:
        if self.graphs.has_graph(network_id):
            return
        self.graphs.create_graph(network_id)
        for node in self.db.nodes.find({"network_id": network_id}):
            self.graphs.add_node(
                network_id, node["id"], name=node["name"], type=node["type"], 
                status=node["status"], created_at=node["created_at"].isoformat()
            )
        for link in self.db.links.find({"network_id": network_id}):
            self.graphs.add_link(
                network_id, link["id"], link["source_node_id"], link["destination_node_id"],
                bandwidth=link["bandwidth"], latency=link["latency"], packet_loss=link["packet_loss"], status=link["status"]
            )
