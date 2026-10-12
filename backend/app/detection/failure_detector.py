import networkx as nx
from app.enums import ElementStatus, FailureSeverity, FailureType

class FailureDetector:
    def __init__(self, baseline_nodes: list[dict], baseline_links: list[dict], current_nodes: list[dict], current_links: list[dict]):
        self.baseline_nodes_map = {n.get("node_id", n.get("id")): n for n in baseline_nodes}
        self.baseline_links_map = {l.get("link_id", l.get("id")): l for l in baseline_links}
        self.current_nodes_map = {n["id"]: n for n in current_nodes}
        self.current_links_map = {l["id"]: l for l in current_links}
        
        self.baseline_graph = self._build_baseline_graph(baseline_nodes, baseline_links)
        self.current_graph = self._build_current_graph(current_nodes, current_links)
        self.active_graph = self._build_active_graph(current_nodes, current_links)

    def detect_failed_nodes(self) -> list:
        failures = []
        for node_id, current_node in self.current_nodes_map.items():
            baseline_node = self.baseline_nodes_map.get(node_id)
            if current_node["status"] == ElementStatus.FAILED.value and (baseline_node and baseline_node["status"] != ElementStatus.FAILED.value):
                failures.append({
                    "failure_type": FailureType.NODE_FAILURE.value,
                    "target_type": "node",
                    "target_id": node_id,
                    "severity": FailureSeverity.CRITICAL.value,
                    "description": f"Node {current_node.get('name', node_id)} failed"
                })
        return failures

    def detect_failed_links(self) -> list:
        failures = []
        for link_id, current_link in self.current_links_map.items():
            baseline_link = self.baseline_links_map.get(link_id)
            if current_link["status"] == ElementStatus.FAILED.value and (baseline_link and baseline_link["status"] != ElementStatus.FAILED.value):
                failures.append({
                    "failure_type": FailureType.LINK_FAILURE.value,
                    "target_type": "link",
                    "target_id": link_id,
                    "severity": FailureSeverity.CRITICAL.value,
                    "description": f"Link {link_id} failed"
                })
        return failures

    def detect_degraded_links(self, latency_threshold_pct=20, packet_loss_threshold_abs=5.0, bandwidth_threshold_pct=20) -> list:
        failures = []
        for link_id, current_link in self.current_links_map.items():
            baseline_link = self.baseline_links_map.get(link_id)
            if not baseline_link or current_link["status"] == ElementStatus.FAILED.value:
                continue

            degradations = []
            if current_link["packet_loss"] > baseline_link["packet_loss"] + packet_loss_threshold_abs:
                degradations.append(f"packet loss increased (baseline: {baseline_link['packet_loss']}%, current: {current_link['packet_loss']}%)")
            
            if baseline_link["latency"] > 0 and current_link["latency"] > baseline_link["latency"] * (1 + latency_threshold_pct/100):
                degradations.append(f"latency increased (baseline: {baseline_link['latency']}ms, current: {current_link['latency']}ms)")
            
            if baseline_link["bandwidth"] > 0 and current_link["bandwidth"] < baseline_link["bandwidth"] * (1 - bandwidth_threshold_pct/100):
                degradations.append(f"bandwidth decreased (baseline: {baseline_link['bandwidth']}Mbps, current: {current_link['bandwidth']}Mbps)")

            if degradations:
                severity = FailureSeverity.WARNING.value
                failures.append({
                    "failure_type": FailureType.LINK_DEGRADATION.value,
                    "target_type": "link",
                    "target_id": link_id,
                    "severity": severity,
                    "description": f"Link {link_id} degraded: {', '.join(degradations)}"
                })
        return failures

    def detect_partitions(self) -> tuple:
        G = self.active_graph.to_undirected() if self.active_graph.is_directed() else self.active_graph
        components = list(nx.connected_components(G))
        comp_count = len(components)
        
        failures = []
        if comp_count > 1:
            failures.append({
                "failure_type": FailureType.NETWORK_PARTITION.value,
                "target_type": "network",
                "severity": FailureSeverity.CRITICAL.value,
                "description": f"Network partitioned into {comp_count} components"
            })
        return comp_count, components, failures

    def check_connectivity(self, source_id: str, destination_id: str) -> bool:
        if source_id not in self.active_graph or destination_id not in self.active_graph:
            return False
        return nx.has_path(self.active_graph, source_id, destination_id)

    def detect_unreachable_pairs(self) -> int:
        components = list(nx.connected_components(self.active_graph.to_undirected()))
        unreachable = 0
        comp_sizes = [len(c) for c in components]
        total_nodes = sum(comp_sizes)
        for size in comp_sizes:
            unreachable += size * (total_nodes - size)
        return unreachable // 2

    def get_affected_simulations(self, previous_simulations: list) -> list:
        affected = []
        for sim in previous_simulations:
            if sim.get("status") == "failed":
                continue

            route_nodes = self._extract_route(sim)
            if not route_nodes:
                continue

            impacts = []
            impact_type = None

            route_failed = False
            for node_id in route_nodes:
                current_node = self.current_nodes_map.get(node_id)
                if current_node and current_node["status"] == ElementStatus.FAILED.value:
                    if not impact_type:
                        impact_type = FailureType.ROUTE_UNAVAILABLE.value
                    impacts.append(f"Route contains failed node {node_id}")
                    route_failed = True

            for i in range(len(route_nodes) - 1):
                u = route_nodes[i]
                v = route_nodes[i+1]
                for link in self.current_links_map.values():
                    if (link["source_node_id"] == u and link["destination_node_id"] == v) or (link["source_node_id"] == v and link["destination_node_id"] == u):
                        if link["status"] == ElementStatus.FAILED.value:
                            if not impact_type or impact_type != FailureType.ROUTE_UNAVAILABLE.value:
                                impact_type = FailureType.ROUTE_UNAVAILABLE.value
                            impacts.append(f"Route contains failed link {link['id']}")
                        else:
                            baseline_link = self.baseline_links_map.get(link["id"])
                            if baseline_link:
                                if link["latency"] > baseline_link["latency"] * 1.2 or link["packet_loss"] > baseline_link["packet_loss"] + 5.0 or link["bandwidth"] < baseline_link["bandwidth"] * 0.8:
                                    if not impact_type and impact_type != FailureType.ROUTE_UNAVAILABLE.value:
                                        impact_type = FailureType.ROUTE_DEGRADED.value
                                    impacts.append(f"Route contains degraded link {link['id']}")
                
            if impacts:
                affected.append({
                    "simulation_id": sim["id"],
                    "source": sim["source_node_id"],
                    "destination": sim["destination_node_id"],
                    "original_route": route_nodes,
                    "impact": impact_type,
                    "reason": ", ".join(impacts)
                })

        return affected
    
    def _extract_route(self, sim):
        return sim.get("route_nodes", [])

    def _build_baseline_graph(self, nodes, links) -> nx.Graph:
        G = nx.Graph()
        for node in nodes:
            G.add_node(node.get("node_id", node.get("id")))
        return G

    def _build_current_graph(self, nodes, links) -> nx.Graph:
        G = nx.Graph()
        for node in nodes:
            G.add_node(node["id"])
        for link in links:
            G.add_edge(link["source_node_id"], link["destination_node_id"], id=link["id"])
        return G

    def _build_active_graph(self, nodes, links) -> nx.Graph:
        G = nx.Graph()
        for node in nodes:
            if node["status"] != ElementStatus.FAILED.value:
                G.add_node(node["id"])
        for link in links:
            if link["status"] != ElementStatus.FAILED.value:
                if G.has_node(link["source_node_id"]) and G.has_node(link["destination_node_id"]):
                    G.add_edge(link["source_node_id"], link["destination_node_id"], id=link["id"])
        return G
