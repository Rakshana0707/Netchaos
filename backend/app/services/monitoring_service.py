"""Module 6 - Network Monitoring Service"""
from datetime import datetime, timezone
import networkx as nx
from pymongo.database import Database

from app.enums import ElementStatus
from app.errors import NotFoundError
from app.schemas.monitoring import (
    HealthStatus, NodeMetrics, LinkMetrics, TrafficMetricsSummary,
    ConnectivityMetrics, MonitoringSnapshot, SingleLinkMetrics,
    SingleNodeMetrics, RecoverySummary, ChaosPhaseMetrics,
    ChaosImpactComparison, AffectedFlow, PartitionInfo, MonitoringConfig
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

class HealthEvaluator:
    def __init__(self, config: MonitoringConfig):
        self.config = config

    def evaluate_network(self, nodes: NodeMetrics, links: LinkMetrics, traffic: TrafficMetricsSummary, partitions: int, traffic_availability: float = 100.0) -> HealthStatus:
        # Critical if network is partitioned, nodes are down, traffic availability is 0, or active flows are disrupted
        if partitions > 1 or nodes.failed > 0 or traffic.packet_loss_percentage >= self.config.packet_loss_critical or traffic_availability == 0 or traffic.affected_flows > 0:
            return HealthStatus.CRITICAL

        # Degraded if physical link is failed/degraded but traffic has been recovered around it (reduced redundancy)
        if links.failed > 0 or links.degraded > 0 or traffic.packet_loss_percentage >= self.config.packet_loss_warning or traffic_availability < 100.0:
            return HealthStatus.DEGRADED
            
        return HealthStatus.HEALTHY

    def evaluate_link(self, current: dict, baseline: dict | None) -> HealthStatus:
        if current.get("status") == ElementStatus.FAILED.value:
            return HealthStatus.CRITICAL
            
        if baseline:
            loss_diff = current.get("packet_loss", 0.0) - baseline.get("packet_loss", 0.0)
            if loss_diff >= self.config.packet_loss_critical:
                return HealthStatus.CRITICAL
            elif loss_diff >= self.config.packet_loss_warning:
                return HealthStatus.DEGRADED
                
            base_lat = baseline.get("latency", 0.0)
            if base_lat > 0:
                lat_inc = ((current.get("latency", 0.0) - base_lat) / base_lat) * 100
                if lat_inc >= self.config.latency_critical_percent:
                    return HealthStatus.CRITICAL
                elif lat_inc >= self.config.latency_warning_percent:
                    return HealthStatus.DEGRADED
                    
            base_bw = baseline.get("bandwidth", 0.0)
            if base_bw > 0:
                bw_dec = ((base_bw - current.get("bandwidth", 0.0)) / base_bw) * 100
                if bw_dec >= self.config.throughput_warning_percent:
                    return HealthStatus.DEGRADED
                    
        return HealthStatus.HEALTHY

class MonitoringService:
    def __init__(self, db: Database):
        self.db = db
        self.config = MonitoringConfig()
        self.evaluator = HealthEvaluator(self.config)

    def _get_network(self, network_id: str):
        net = self.db.networks.find_one({"id": network_id})
        if not net:
            raise NotFoundError(f"Network {network_id} not found", "network_not_found")
        return net

    def get_current_metrics(self, network_id: str) -> dict:
        self._get_network(network_id)
        
        # Nodes
        nodes = list(self.db.nodes.find({"network_id": network_id}))
        total_nodes = len(nodes)
        active_nodes = sum(1 for n in nodes if n.get("status") == ElementStatus.ACTIVE.value)
        failed_nodes = sum(1 for n in nodes if n.get("status") == ElementStatus.FAILED.value)
        node_metrics = NodeMetrics(total=total_nodes, active=active_nodes, failed=failed_nodes)

        # Links
        links = list(self.db.links.find({"network_id": network_id}))
        total_links = len(links)
        active_links = sum(1 for l in links if l.get("status") == ElementStatus.ACTIVE.value)
        failed_links = sum(1 for l in links if l.get("status") == ElementStatus.FAILED.value)

        # To find degraded, we need the baseline
        baseline = self.db.network_baselines.find_one({"network_id": network_id, "is_active": True})
        degraded_links = 0
        if baseline:
            base_links_map = {l["link_id"]: l for l in baseline.get("links", [])}
            for l in links:
                if l.get("status") != ElementStatus.FAILED.value:
                    b = base_links_map.get(l["id"])
                    if self.evaluator.evaluate_link(l, b) == HealthStatus.DEGRADED:
                        degraded_links += 1
                        
        link_metrics = LinkMetrics(total=total_links, active=active_links, failed=failed_links, degraded=degraded_links)

        # Traffic
        sims = list(self.db.traffic_simulations.find({"network_id": network_id, "status": "completed"}))
        active_flows = len(sims)

        links_by_pair = {
            tuple(sorted([l["source_node_id"], l["destination_node_id"]])): l
            for l in links
        }

        total_packets = 0
        dropped_packets = 0
        total_lat = 0.0
        total_throughput = 0.0

        for s in sims:
            route = s.get("route") or []
            pkt_count = s.get("packet_count", 10)
            total_packets += pkt_count

            route_delivery_prob = 1.0
            route_lat = 0.0
            route_bw = float("inf")
            route_failed = False

            if route and len(route) >= 2:
                for i in range(len(route) - 1):
                    pair = tuple(sorted([route[i], route[i+1]]))
                    link_obj = links_by_pair.get(pair)
                    if link_obj:
                        if link_obj.get("status") == ElementStatus.FAILED.value:
                            route_failed = True
                        loss_rate = link_obj.get("packet_loss", 0.0) / 100.0
                        route_delivery_prob *= max(0.0, 1.0 - loss_rate)
                        route_lat += link_obj.get("latency", 0.0)
                        route_bw = min(route_bw, link_obj.get("bandwidth", 100.0))
            else:
                route_lat = s.get("path_latency_ms", 0.0)
                route_bw = s.get("path_bandwidth_mbps", 0.0)

            if route_failed:
                loss_pct = 100.0
            else:
                loss_pct = round((1.0 - route_delivery_prob) * 100.0, 2)

            effective_loss = loss_pct
            flow_dropped = round(pkt_count * (effective_loss / 100.0))
            dropped_packets += flow_dropped
            total_lat += route_lat if route_lat > 0 else s.get("path_latency_ms", 0.0)
            total_throughput += (route_bw if route_bw < float("inf") else s.get("path_bandwidth_mbps", 0.0))

        delivered_packets = total_packets - dropped_packets
        packet_loss_percentage = 0.0
        if total_packets > 0:
            packet_loss_percentage = round((dropped_packets / total_packets) * 100, 2)
        elif not sims and links:
            avg_link_loss = sum(l.get("packet_loss", 0.0) for l in links) / len(links)
            packet_loss_percentage = round(avg_link_loss, 2)

        avg_lat = round(total_lat / active_flows, 2) if active_flows > 0 else 0.0
        throughput = round(total_throughput, 2)

        # Affected flows (flows currently impacted by failures or degraded links and not yet recovered)
        affected_flows = 0
        recoveries = list(self.db.recovery_events.find({"network_id": network_id}).sort("created_at", -1))
        latest_rec_map = {}
        for r in recoveries:
            sid = r["simulation_id"]
            if sid not in latest_rec_map:
                latest_rec_map[sid] = r

        failed_node_ids = {n["id"] for n in nodes if n.get("status") == ElementStatus.FAILED.value}
        failed_or_degraded_link_keys = {
            tuple(sorted([l["source_node_id"], l["destination_node_id"]]))
            for l in links if l.get("status") == ElementStatus.FAILED.value or l.get("packet_loss", 0.0) > 1.0
        }

        for s in sims:
            r = latest_rec_map.get(s["id"])
            if r and r.get("recovery_status") == "RECOVERED" and r.get("connectivity_restored"):
                rec_route = r.get("recovered_route") or s.get("route") or []
                # Check if recovered route is clean
                is_clean = True
                for i in range(len(rec_route) - 1):
                    pair = tuple(sorted([rec_route[i], rec_route[i+1]]))
                    if pair in failed_or_degraded_link_keys:
                        is_clean = False
                        break
                if is_clean:
                    continue

            route = s.get("route") or []
            is_disrupted = not s.get("route_available", True)
            if not is_disrupted and route:
                for nid in route:
                    if nid in failed_node_ids:
                        is_disrupted = True
                        break
                if not is_disrupted:
                    for i in range(len(route) - 1):
                        pair = tuple(sorted([route[i], route[i+1]]))
                        if pair in failed_or_degraded_link_keys:
                            is_disrupted = True
                            break
            if is_disrupted:
                affected_flows += 1
                
        traffic_metrics = TrafficMetricsSummary(
            active_flows=active_flows,
            affected_flows=affected_flows,
            total_packets=total_packets,
            delivered_packets=delivered_packets,
            dropped_packets=dropped_packets,
            packet_loss_percentage=packet_loss_percentage,
            average_latency=round(avg_lat, 2),
            throughput=round(throughput, 2)
        )
        
        # Connectivity
        # Build active graph
        G = nx.Graph()
        for n in nodes:
            if n.get("status") != ElementStatus.FAILED.value:
                G.add_node(n["id"])
        for l in links:
            if l.get("status") != ElementStatus.FAILED.value:
                if G.has_node(l["source_node_id"]) and G.has_node(l["destination_node_id"]):
                    G.add_edge(l["source_node_id"], l["destination_node_id"])
                    
        partitions = max(1, nx.number_connected_components(G)) if nodes else 1
        
        traffic_availability = 0.0
        if active_flows > 0:
            successful = sum(1 for s in sims if s.get("route_available", True) and s.get("path_latency_ms") is not None)
            traffic_availability = round((successful / active_flows) * 100, 2)
        elif active_flows == 0 and total_nodes > 0:
            traffic_availability = 100.0
            
        conn_metrics = ConnectivityMetrics(
            partitions=partitions,
            traffic_availability=traffic_availability
        )

        
        status = self.evaluator.evaluate_network(node_metrics, link_metrics, traffic_metrics, partitions, traffic_availability)

        
        return {
            "network_id": network_id,
            "timestamp": _utcnow(),
            "health_status": status,
            "nodes": node_metrics.dict(),
            "links": link_metrics.dict(),
            "traffic": traffic_metrics.dict(),
            "connectivity": conn_metrics.dict()
        }

    def create_snapshot(self, network_id: str) -> MonitoringSnapshot:
        metrics = self.get_current_metrics(network_id)
        
        suffix = network_id[-3:] if len(network_id) >= 3 else "net"
        count = self.db.monitoring_snapshots.count_documents({"network_id": network_id})
        metrics["id"] = f"snap_{suffix}_{count + 1:03d}"
        
        self.db.monitoring_snapshots.insert_one(metrics.copy())
        
        metrics.pop("_id", None)
        return MonitoringSnapshot(**metrics)

    def get_history(self, network_id: str, limit: int = 50) -> list[MonitoringSnapshot]:
        self._get_network(network_id)
        docs = list(self.db.monitoring_snapshots.find({"network_id": network_id}).sort("timestamp", -1).limit(limit))
        if not docs:
            initial_snap = self.create_snapshot(network_id)
            docs = [initial_snap.dict()]
        return [MonitoringSnapshot(**d) for d in docs]
        
    def get_links(self, network_id: str) -> list[SingleLinkMetrics]:
        self._get_network(network_id)
        links = list(self.db.links.find({"network_id": network_id}))
        baseline = self.db.network_baselines.find_one({"network_id": network_id, "is_active": True})
        base_map = {l["link_id"]: l for l in baseline.get("links", [])} if baseline else {}
        
        res = []
        for l in links:
            b = base_map.get(l["id"])
            health = self.evaluator.evaluate_link(l, b)
            
            b_lat = b.get("latency") if b else None
            b_bw = b.get("bandwidth") if b else None
            b_pl = b.get("packet_loss") if b else None
            
            lat_change = None
            if b_lat and b_lat > 0:
                lat_change = round(((l.get("latency", 0) - b_lat) / b_lat) * 100, 2)
                
            bw_change = None
            if b_bw and b_bw > 0:
                bw_change = round(((l.get("bandwidth", 0) - b_bw) / b_bw) * 100, 2)
                
            pl_change = None
            if b_pl is not None:
                pl_change = round(l.get("packet_loss", 0) - b_pl, 2)
                
            res.append(SingleLinkMetrics(
                link_id=l["id"],
                source=l["source_node_id"],
                destination=l["destination_node_id"],
                status=l["status"],
                bandwidth=l.get("bandwidth", 0),
                latency=l.get("latency", 0),
                packet_loss=l.get("packet_loss", 0),
                baseline_bandwidth=b_bw,
                baseline_latency=b_lat,
                baseline_packet_loss=b_pl,
                bandwidth_change_percent=bw_change,
                latency_change_percent=lat_change,
                packet_loss_change=pl_change,
                health_status=health
            ))
        return res
        
    def get_nodes(self, network_id: str) -> list[SingleNodeMetrics]:
        self._get_network(network_id)
        nodes = list(self.db.nodes.find({"network_id": network_id}))
        links = list(self.db.links.find({"network_id": network_id}))
        
        res = []
        for n in nodes:
            c_links = [l for l in links if l["source_node_id"] == n["id"] or l["destination_node_id"] == n["id"]]
            f_links = sum(1 for l in c_links if l.get("status") == ElementStatus.FAILED.value)
            
            status = HealthStatus.HEALTHY
            if n.get("status") == ElementStatus.FAILED.value:
                status = HealthStatus.CRITICAL
            elif f_links > 0:
                status = HealthStatus.DEGRADED
                
            res.append(SingleNodeMetrics(
                node_id=n["id"],
                status=n["status"],
                connected_links=len(c_links),
                failed_links=f_links,
                affected_traffic_count=0, # Simplified
                health_status=status
            ))
        return res
        
    def get_recovery_summary(self, network_id: str) -> RecoverySummary:
        self._get_network(network_id)
        events = list(self.db.recovery_events.find({"network_id": network_id}))
        
        total = len(events)
        if total == 0:
            return RecoverySummary(
                total_recovery_events=0, successful_recoveries=0, failed_recoveries=0,
                average_recovery_time=0.0, minimum_recovery_time=None, maximum_recovery_time=None,
                connectivity_restored_percentage=0.0
            )
            
        success = [e for e in events if e.get("recovery_status") == "RECOVERED"]
        failed = total - len(success)
        times = [e.get("recovery_duration", 0) for e in events if e.get("recovery_duration") is not None]
        
        avg_time = sum(times) / len(times) if times else 0.0
        min_time = min(times) if times else None
        max_time = max(times) if times else None
        ratio = (len(success) / total) * 100
        
        return RecoverySummary(
            total_recovery_events=total,
            successful_recoveries=len(success),
            failed_recoveries=failed,
            average_recovery_time=round(avg_time, 4),
            minimum_recovery_time=round(min_time, 4) if min_time else None,
            maximum_recovery_time=round(max_time, 4) if max_time else None,
            connectivity_restored_percentage=round(ratio, 2)
        )
