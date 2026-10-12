"""In-memory NetworkX topology, one undirected graph per network.

This layer knows nothing about FastAPI or SQLAlchemy: it stores plain attribute
dictionaries. The service layer keeps it in sync with the database.

Later modules (routing, failure simulation, ...) should call ``get_graph`` and treat
the result as read-only, using ``graph.copy()`` for what-if analysis. All changes
must go through the methods below so the database and graph stay consistent.
"""
from collections.abc import Mapping
from threading import RLock
from typing import Any

import networkx as nx


class GraphError(Exception):
    """Raised when a graph operation is invalid (unknown network, node or link)."""


class GraphManager:
    def __init__(self) -> None:
        self._graphs: dict[str, nx.Graph] = {}
        self._lock = RLock()

    # --- graph lifecycle -------------------------------------------------
    def create_graph(self, network_id: str) -> nx.Graph:
        with self._lock:
            if network_id in self._graphs:
                raise GraphError(f"Graph for network '{network_id}' already exists")
            graph = nx.Graph(network_id=network_id)
            self._graphs[network_id] = graph
            return graph

    def has_graph(self, network_id: str) -> bool:
        return network_id in self._graphs

    def get_graph(self, network_id: str) -> nx.Graph:
        try:
            return self._graphs[network_id]
        except KeyError:
            raise GraphError(f"Graph for network '{network_id}' is not loaded") from None

    def snapshot(self, network_id: str) -> nx.Graph:
        """Independent copy of a network's graph, taken under the lock.

        Consumers such as the traffic simulator work on a snapshot so that a topology
        change made while they run cannot corrupt (or half-apply to) their calculation.
        """
        with self._lock:
            return self.get_graph(network_id).copy()

    def drop_graph(self, network_id: str) -> None:
        """Forget one network's graph so it is rebuilt from the database on next use."""
        with self._lock:
            self._graphs.pop(network_id, None)

    def clear(self) -> None:
        """Drop every graph (e.g. tests, or forcing a rebuild from the database)."""
        with self._lock:
            self._graphs.clear()

    # --- nodes -----------------------------------------------------------
    def add_node(self, network_id: str, node_id: str, **attributes: Any) -> None:
        with self._lock:
            graph = self.get_graph(network_id)
            if graph.has_node(node_id):
                raise GraphError(f"Node '{node_id}' already exists")
            graph.add_node(node_id, **attributes)

    def remove_node(self, network_id: str, node_id: str) -> None:
        """Remove a node together with every link attached to it."""
        with self._lock:
            graph = self.get_graph(network_id)
            if not graph.has_node(node_id):
                raise GraphError(f"Node '{node_id}' does not exist")
            graph.remove_node(node_id)

    def get_nodes(self, network_id: str) -> list[dict[str, Any]]:
        graph = self.get_graph(network_id)
        return [{"node_id": node_id, **attrs} for node_id, attrs in graph.nodes(data=True)]

    # --- links -----------------------------------------------------------
    def add_link(self, network_id: str, link_id: str, source: str, destination: str, **attributes: Any) -> None:
        with self._lock:
            graph = self.get_graph(network_id)
            for endpoint in (source, destination):
                if not graph.has_node(endpoint):
                    raise GraphError(f"Node '{endpoint}' does not exist")
            if source == destination:
                raise GraphError("A link cannot connect a node to itself")
            if graph.has_edge(source, destination):
                raise GraphError(f"Nodes '{source}' and '{destination}' are already linked")
            graph.add_edge(source, destination, link_id=link_id, **attributes)

    def remove_link(self, network_id: str, link_id: str) -> None:
        with self._lock:
            graph = self.get_graph(network_id)
            for source, destination, attrs in graph.edges(data=True):
                if attrs["link_id"] == link_id:
                    graph.remove_edge(source, destination)
                    return
            raise GraphError(f"Link '{link_id}' does not exist")

    def get_links(self, network_id: str) -> list[dict[str, Any]]:
        graph = self.get_graph(network_id)
        return [
            {"source": source, "destination": destination, **attrs}
            for source, destination, attrs in graph.edges(data=True)
        ]

    # --- state updates (used by the chaos module) --------------------------------
    def update_elements(
        self,
        network_id: str,
        node_updates: Mapping[str, Mapping[str, Any]] | None = None,
        link_updates: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Set attributes on existing nodes and links (by node id / link id) in one locked step.

        Everything is checked before anything is changed, so an unknown id leaves the graph untouched.
        """
        node_updates, link_updates = node_updates or {}, link_updates or {}
        with self._lock:
            graph = self.get_graph(network_id)
            for node_id in node_updates:
                if not graph.has_node(node_id):
                    raise GraphError(f"Node '{node_id}' does not exist")
            edges = {attrs["link_id"]: (u, v) for u, v, attrs in graph.edges(data=True)}
            for link_id in link_updates:
                if link_id not in edges:
                    raise GraphError(f"Link '{link_id}' does not exist")
            for node_id, attrs in node_updates.items():
                graph.nodes[node_id].update(attrs)
            for link_id, attrs in link_updates.items():
                u, v = edges[link_id]
                graph[u][v].update(attrs)
