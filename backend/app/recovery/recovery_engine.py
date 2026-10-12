"""Recovery Engine: given the current operational graph and a failed simulation route,
finds the best alternative route using the chosen strategy.

This class does NOT touch the database or FastAPI request objects — it only works
with plain Python data structures and NetworkX graphs.
"""
from __future__ import annotations

import itertools

import networkx as nx

from app.schemas.recovery import RecoveryStrategy


class RouteCandidate:
    """A candidate alternative route with computed cost metrics."""

    def __init__(self, path: list[str], latency: float, hop_count: int, bandwidth: float) -> None:
        self.path = path
        self.latency = latency
        self.hop_count = hop_count
        self.bandwidth = bandwidth


class RecoveryEngine:
    """Finds the best alternative route on the operational graph.

    The operational graph already excludes failed nodes and failed links
    (built by the caller from the current DB state).
    """

    def __init__(self, operational_graph: nx.Graph) -> None:
        self.G = operational_graph

    def is_route_valid(self, route: list[str]) -> bool:
        """True if every node and every consecutive edge pair in the route exists on the operational graph."""
        if not route or len(route) < 2:
            return False
        for node in route:
            if node not in self.G:
                return False
        for i in range(len(route) - 1):
            if not self.G.has_edge(route[i], route[i + 1]):
                return False
        return True

    def find_best_route(
        self,
        source: str,
        destination: str,
        strategy: RecoveryStrategy,
        latency_weight: float = 1.0,
        hop_weight: float = 2.0,
        bandwidth_weight: float = 0.5,
    ) -> RouteCandidate | None:
        """Find the best route from source to destination using the given strategy.

        Returns None if no route is reachable.
        """
        if source not in self.G or destination not in self.G:
            return None

        if strategy == RecoveryStrategy.SHORTEST_HOP:
            return self._shortest_hop(source, destination)
        elif strategy == RecoveryStrategy.LOWEST_LATENCY:
            return self._lowest_latency(source, destination)
        elif strategy == RecoveryStrategy.HIGHEST_BANDWIDTH:
            return self._highest_bandwidth(source, destination)
        elif strategy == RecoveryStrategy.COMPOSITE:
            return self._composite(source, destination, latency_weight, hop_weight, bandwidth_weight)
        else:
            return self._shortest_hop(source, destination)

    def _shortest_hop(self, source: str, destination: str) -> RouteCandidate | None:
        """Minimize number of hops (nx.shortest_path with no weight = BFS)."""
        try:
            path = nx.shortest_path(self.G, source, destination)
            return self._make_candidate(path)
        except nx.NetworkXNoPath:
            return None
        except nx.NodeNotFound:
            return None

    def _lowest_latency(self, source: str, destination: str) -> RouteCandidate | None:
        """Minimize sum of link latencies."""
        try:
            # Weight by latency; ties broken by node id order (deterministic)
            path = nx.shortest_path(self.G, source, destination, weight="latency")
            return self._make_candidate(path)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def _highest_bandwidth(self, source: str, destination: str) -> RouteCandidate | None:
        """Maximize the bottleneck bandwidth (exact, polynomial time).

        Try each distinct link bandwidth from highest to lowest: the first threshold at which source and
        destination are still connected using only links at or above it is the best achievable bottleneck.
        Among routes with that bottleneck the fewest-hop route is returned.
        """
        if source not in self.G or destination not in self.G:
            return None
        for threshold in sorted({d.get("bandwidth", 0.0) for _, _, d in self.G.edges(data=True)}, reverse=True):
            usable = nx.Graph()
            usable.add_nodes_from(self.G.nodes)
            usable.add_edges_from((u, v) for u, v, d in self.G.edges(data=True) if d.get("bandwidth", 0.0) >= threshold)
            if nx.has_path(usable, source, destination):
                return self._make_candidate(nx.shortest_path(usable, source, destination))
        return None

    #: Upper bound on candidate routes examined by the composite strategy (keeps meshes tractable).
    MAX_COMPOSITE_CANDIDATES = 500

    def _composite(
        self,
        source: str,
        destination: str,
        latency_weight: float,
        hop_weight: float,
        bandwidth_weight: float,
    ) -> RouteCandidate | None:
        """Composite cost: latency_weight*latency + hop_weight*hops + a penalty for low bandwidth.

        The cost is not a plain shortest-path weight, so candidates are the ``MAX_COMPOSITE_CANDIDATES``
        lowest-latency simple routes (enumerated lazily); the cheapest of those under the composite
        cost is returned. On very large meshes this is a documented approximation.
        """
        if source not in self.G or destination not in self.G or not nx.has_path(self.G, source, destination):
            return None
        best: RouteCandidate | None = None
        best_cost = float("inf")
        paths = nx.shortest_simple_paths(self.G, source, destination, weight="latency")
        for path in itertools.islice(paths, self.MAX_COMPOSITE_CANDIDATES):
            c = self._make_candidate(path)
            bw_penalty = (1.0 / max(c.bandwidth, 0.001)) * bandwidth_weight * 1000
            cost = latency_weight * c.latency + hop_weight * c.hop_count + bw_penalty
            if best is None or cost < best_cost or (cost == best_cost and path < best.path):
                best, best_cost = c, cost
        return best

    def _make_candidate(self, path: list[str]) -> RouteCandidate:
        latency = 0.0
        bandwidth = float("inf")
        for i in range(len(path) - 1):
            edge_data = self.G[path[i]][path[i + 1]]
            latency += edge_data.get("latency", 0.0)
            bw = edge_data.get("bandwidth", float("inf"))
            bandwidth = min(bandwidth, bw)
        hop_count = len(path) - 1
        if bandwidth == float("inf"):
            bandwidth = 0.0
        return RouteCandidate(path=path, latency=latency, hop_count=hop_count, bandwidth=bandwidth)

    def compute_route_metrics(self, route: list[str]) -> tuple[float, int, float]:
        """Return (total_latency, hop_count, bottleneck_bandwidth) for a route on the operational graph."""
        if not route or len(route) < 2:
            return 0.0, 0, 0.0
        latency = 0.0
        bandwidth = float("inf")
        for i in range(len(route) - 1):
            if not self.G.has_edge(route[i], route[i + 1]):
                return 0.0, 0, 0.0
            edge = self.G[route[i]][route[i + 1]]
            latency += edge.get("latency", 0.0)
            bandwidth = min(bandwidth, edge.get("bandwidth", float("inf")))
        if bandwidth == float("inf"):
            bandwidth = 0.0
        return latency, len(route) - 1, bandwidth
