"""Deterministic traffic simulator (Module 2).

Pure simulation logic: no FastAPI, no SQLAlchemy. It takes a NetworkX graph, works on its own
copy of it ("snapshot"), and never touches a database while packets are processed.

Simulation model (a controlled model, NOT a measurement of real network behaviour)
---------------------------------------------------------------------------------
* The route is found once with ``networkx.shortest_path`` over the *whole* topology, failed nodes and
  links included (it is "the current route"). If that route crosses a failed node or link the simulation
  fails with a clear reason. There is NO rerouting: finding a way around a failure is Module 5's job.
* All packets are queued at the source at t = 0 and sent back to back.
* Links are full duplex; only the source -> destination direction is used.
* Each link is a store-and-forward stage. A packet crossing link *i*:

      start      = max(time the packet is ready at this node, time the link becomes free)
      link busy  = start .. start + tx_time
      tx_time    = packet_size_bits / link_bandwidth                (serialisation delay)
      ready next = start + tx_time + link_latency + processing_overhead

* Loss: while crossing each link a packet is dropped with probability ``packet_loss / 100``.
  A dropped packet still occupies the link for its tx_time but goes no further.
* ``simulated_duration_ms`` is the simulated time at which the last packet was delivered or
  dropped. It is model time, unrelated to how long the Python code ran (that is
  ``execution_duration_ms``, measured by the caller).
* Throughput = delivered bytes * 8 / simulated duration.

Link properties (bandwidth, latency, packet_loss, status) are read from the graph each time a
``TrafficSimulator`` is built, never cached or hard-coded, so anything that changes the graph
(the chaos module) is picked up by the next simulation automatically.
"""
import random
from collections.abc import Sequence
from dataclasses import dataclass

import networkx as nx

from app.enums import ElementStatus, PacketStatus

# Time a node spends handling a packet before it can start forwarding it. Small and constant.
DEFAULT_PROCESSING_OVERHEAD_MS = 0.05

NO_ROUTE_REASON = "No route available between source and destination"
NODE_FAILED_REASON = "Current route contains failed node"
LINK_FAILED_REASON = "Current route contains failed link"

_ACTIVE = ElementStatus.ACTIVE.value


class RouteUnavailableError(Exception):
    """No usable route exists; the message is the human-readable reason."""


@dataclass(frozen=True, slots=True)
class LinkState:
    """The properties of one link at the moment the simulator took its snapshot."""
    link_id: str
    source: str
    destination: str
    bandwidth_mbps: float
    latency_ms: float
    packet_loss_percent: float


@dataclass(frozen=True)
class RouteInfo:
    """Everything a caller (or the future recovery module) needs to know about a route."""
    source: str
    destination: str
    available: bool
    route: list[str]
    links: list[LinkState]
    hop_count: int
    latency_ms: float
    bandwidth_mbps: float
    reason: str | None = None
    # Only set when the route exists but cannot be used: the route that was found and the ids of the
    # failed nodes / links on it (for the failure-detection module; not stored with the simulation).
    blocked_route: list[str] | None = None
    failed_nodes: tuple[str, ...] = ()
    failed_links: tuple[str, ...] = ()


@dataclass(slots=True)
class PacketResult:
    sequence_number: int
    status: PacketStatus
    completed_at_ms: float  # simulated time of delivery, or of the drop
    dropped_at_link_id: str | None = None


@dataclass
class SimulationOutcome:
    """Raw result of simulate_traffic; turn it into metrics with calculate_metrics."""
    route_info: RouteInfo
    packet_count: int
    packet_size: int
    random_seed: int
    delivered_packets: int
    dropped_packets: int
    simulated_duration_ms: float
    packets: list[PacketResult] | None = None  # only filled when keep_packets=True


@dataclass(frozen=True)
class TrafficMetrics:
    packet_count: int
    delivered_packets: int
    dropped_packets: int
    packet_loss_percentage: float
    total_data_transferred_bytes: int
    path_latency_ms: float
    hop_count: int
    path_bandwidth_mbps: float
    throughput_mbps: float
    simulated_duration_ms: float


class TrafficSimulator:
    def __init__(
        self,
        graph: nx.Graph,
        processing_overhead_ms: float = DEFAULT_PROCESSING_OVERHEAD_MS,
        route_weight: str | None = None,
        max_queue_bytes: int | None = None,
    ) -> None:
        """
        ``route_weight=None`` finds the route with the fewest hops (plain ``shortest_path``);
        ``"latency"`` would minimise total latency instead.
        ``max_queue_bytes`` introduces tail-drop congestion control if set.
        """
        if processing_overhead_ms < 0:
            raise ValueError("processing_overhead_ms must be >= 0")
        self.processing_overhead_ms = processing_overhead_ms
        self.route_weight = route_weight
        self.max_queue_bytes = max_queue_bytes
        self._graph = self._ordered_copy(graph)

    # --- topology snapshot ---------------------------------------------------
    @staticmethod
    def _ordered_copy(graph: nx.Graph) -> nx.Graph:
        """Copy of the whole topology, statuses included.

        Nodes and links are inserted in sorted order, so when several shortest routes tie the same one
        is chosen every time, whatever order the graph was originally built in. Failed elements are
        kept on purpose: the route is calculated as if nothing had failed and is then checked, so a
        failure makes the route unavailable instead of silently sending traffic another way.
        """
        copy = nx.Graph()
        copy.add_nodes_from(sorted((n, dict(attrs)) for n, attrs in graph.nodes(data=True)))
        edges = [(*sorted((u, v)), dict(attrs)) for u, v, attrs in graph.edges(data=True)]
        for u, v, attrs in sorted(edges, key=lambda e: (e[0], e[1])):
            copy.add_edge(u, v, **attrs)
        return copy

    def _failed_nodes(self, route: Sequence[str]) -> tuple[str, ...]:
        return tuple(n for n in route if self._graph.nodes[n].get("status", _ACTIVE) != _ACTIVE)

    def _failed_links(self, route: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            self._graph[u][v]["link_id"] for u, v in zip(route, route[1:])
            if self._graph[u][v].get("status", _ACTIVE) != _ACTIVE
        )

    # --- routing ---------------------------------------------------------------
    def calculate_route(self, source: str, destination: str) -> list[str]:
        """Shortest route (fewest hops) over the whole topology, as node ids.

        Failed nodes and links are NOT skipped, so this is "the current route"; ``analyze_route`` checks
        it for failures. Raises RouteUnavailableError if the nodes are unknown or not connected at all.
        """
        for role, node in (("Source", source), ("Destination", destination)):
            if node not in self._graph:
                raise RouteUnavailableError(f"{role} node '{node}' is not available in the topology")
        try:
            return nx.shortest_path(self._graph, source, destination, weight=self.route_weight)
        except nx.NetworkXNoPath:
            raise RouteUnavailableError(NO_ROUTE_REASON) from None

    def route_links(self, route: Sequence[str]) -> list[LinkState]:
        """The links a route crosses, with their current properties."""
        if len(route) < 2:
            raise ValueError("A route needs at least two nodes")
        links = []
        for u, v in zip(route, route[1:]):
            if not self._graph.has_edge(u, v):
                raise RouteUnavailableError(f"No link between '{u}' and '{v}'")
            attrs = self._graph[u][v]
            if attrs.get("status", _ACTIVE) != _ACTIVE:
                raise RouteUnavailableError(LINK_FAILED_REASON)
            links.append(
                LinkState(
                    link_id=attrs["link_id"], source=u, destination=v,
                    bandwidth_mbps=float(attrs["bandwidth"]), latency_ms=float(attrs["latency"]),
                    packet_loss_percent=float(attrs.get("packet_loss", 0.0)),
                )
            )
        return links

    def calculate_route_latency(self, route: Sequence[str]) -> float:
        """Sum of the latency of every link on the route (milliseconds)."""
        return sum(link.latency_ms for link in self.route_links(route))

    def calculate_path_bandwidth(self, route: Sequence[str]) -> float:
        """The bottleneck: the smallest link bandwidth on the route (Mbps)."""
        return min(link.bandwidth_mbps for link in self.route_links(route))

    def analyze_route(self, source: str, destination: str) -> RouteInfo:
        """Route plus latency, hop count, bandwidth and availability. Never raises for 'no route'."""
        try:
            route = self.calculate_route(source, destination)
        except RouteUnavailableError as exc:
            return RouteInfo(source, destination, False, [], [], 0, 0.0, 0.0, str(exc))
        failed_nodes, failed_links = self._failed_nodes(route), self._failed_links(route)
        if failed_nodes or failed_links:
            return RouteInfo(
                source, destination, False, [], [], 0, 0.0, 0.0,
                NODE_FAILED_REASON if failed_nodes else LINK_FAILED_REASON,
                blocked_route=route, failed_nodes=failed_nodes, failed_links=failed_links,
            )
        links = self.route_links(route)
        return RouteInfo(
            source=source, destination=destination, available=True, route=route, links=links,
            hop_count=len(links),  # number of links, not nodes
            latency_ms=round(sum(l.latency_ms for l in links), 6),
            bandwidth_mbps=min(l.bandwidth_mbps for l in links),
        )

    def analyze_explicit_route(self, source: str, destination: str, route: Sequence[str]) -> RouteInfo:
        """Validate a caller-supplied route (e.g. one chosen by the recovery engine) and describe it.

        The route is used exactly as given or rejected: it must start at ``source``, end at ``destination``,
        follow existing links, and cross no failed node or link. Nothing is ever re-routed here, so a
        failed element can never be used even if a caller passes in a stale route.
        """
        route = list(route)

        def unavailable(reason: str, **extra) -> RouteInfo:
            return RouteInfo(source, destination, False, [], [], 0, 0.0, 0.0, reason, **extra)

        if len(route) < 2 or route[0] != source or route[-1] != destination:
            return unavailable("Supplied route does not connect source to destination")
        for node in route:
            if node not in self._graph:
                return unavailable(f"Node '{node}' on the supplied route is not in the topology")
        if len(set(route)) != len(route):
            return unavailable("Supplied route visits a node more than once")
        for u, v in zip(route, route[1:]):
            if not self._graph.has_edge(u, v):
                return unavailable(f"No link between '{u}' and '{v}' on the supplied route")
        failed_nodes, failed_links = self._failed_nodes(route), self._failed_links(route)
        if failed_nodes or failed_links:
            return unavailable(
                NODE_FAILED_REASON if failed_nodes else LINK_FAILED_REASON,
                blocked_route=route, failed_nodes=failed_nodes, failed_links=failed_links,
            )
        links = self.route_links(route)
        return RouteInfo(
            source=source, destination=destination, available=True, route=route, links=links,
            hop_count=len(links), latency_ms=round(sum(l.latency_ms for l in links), 6),
            bandwidth_mbps=min(l.bandwidth_mbps for l in links),
        )

    # --- packets ---------------------------------------------------------------
    @staticmethod
    def transmission_time_ms(packet_size: int, bandwidth_mbps: float) -> float:
        """Time to put ``packet_size`` bytes on a link: bits / (Mbit/s * 1000) gives milliseconds."""
        return packet_size * 8 / (bandwidth_mbps * 1000.0)

    def simulate_packet(
        self,
        sequence_number: int,
        links: Sequence[LinkState],
        tx_times_ms: Sequence[float],
        rng: random.Random,
        link_free_at: list[float],
        packet_size: int,
    ) -> PacketResult:
        """Send one packet along ``links``. ``link_free_at`` (one entry per link) is updated in place.

        One random number is drawn per link crossed, in route order, which is what makes a run
        reproducible for a given seed.
        """
        ready = 0.0  # packets are all waiting at the source at t = 0
        for i, link in enumerate(links):
            start = max(ready, link_free_at[i])
            
            # Queue management / Tail-Drop Congestion Control
            if self.max_queue_bytes is not None:
                queue_wait = start - ready
                if queue_wait > 0:
                    # Calculate bytes currently in the queue for this link based on wait time and bandwidth
                    queue_bytes = (queue_wait * link.bandwidth_mbps * 1000.0) / 8.0
                    # Plus the packet itself
                    if queue_bytes + packet_size > self.max_queue_bytes:
                        return PacketResult(sequence_number, PacketStatus.DROPPED, ready, link.link_id)

            link_free_at[i] = start + tx_times_ms[i]
            if rng.random() * 100.0 < link.packet_loss_percent:
                return PacketResult(sequence_number, PacketStatus.DROPPED, link_free_at[i], link.link_id)
            ready = link_free_at[i] + link.latency_ms + self.processing_overhead_ms
        return PacketResult(sequence_number, PacketStatus.DELIVERED, ready)

    def simulate_traffic(
        self,
        source: str,
        destination: str,
        packet_count: int,
        packet_size: int,
        random_seed: int,
        keep_packets: bool = False,
        route: Sequence[str] | None = None,
    ) -> SimulationOutcome:
        """Send ``packet_count`` packets of ``packet_size`` bytes from source to destination.

        By default the route is the current shortest route (``analyze_route``). If ``route`` is given
        (post-recovery traffic) exactly that route is used after validation (``analyze_explicit_route``).
        Raises RouteUnavailableError if the route cannot be used. The simulator itself never reroutes.
        """
        # Dynamic OSPF/BGP Convergence Blackout
        convergence_blackout_ms = 0.0
        if route is not None:
            # Add 50ms of convergence delay per hop when using a recovered route
            convergence_blackout_ms = (len(route) - 1) * 50.0
        if packet_count <= 0 or packet_size <= 0:
            raise ValueError("packet_count and packet_size must be > 0")
        info = (
            self.analyze_explicit_route(source, destination, route) if route is not None
            else self.analyze_route(source, destination)
        )
        if not info.available:
            raise RouteUnavailableError(info.reason or NO_ROUTE_REASON)

        rng = random.Random(random_seed)
        links = info.links
        tx_times = [self.transmission_time_ms(packet_size, l.bandwidth_mbps) for l in links]
        link_free_at = [0.0] * len(links)

        delivered = 0
        last_event_ms = 0.0
        kept: list[PacketResult] | None = [] if keep_packets else None
        for sequence in range(1, packet_count + 1):
            result = self.simulate_packet(sequence, links, tx_times, rng, link_free_at, packet_size)
            
            # Packets arriving before routing tables converge are dropped!
            if result.completed_at_ms < convergence_blackout_ms and result.status == PacketStatus.DELIVERED:
                result.status = PacketStatus.DROPPED
                result.dropped_at_link_id = "convergence_blackout"

            if result.status is PacketStatus.DELIVERED:
                delivered += 1
            if result.completed_at_ms > last_event_ms:
                last_event_ms = result.completed_at_ms
            if kept is not None:
                kept.append(result)

        # Force simulated duration to at least the blackout time so throughput calculations are accurate
        if last_event_ms < convergence_blackout_ms:
            last_event_ms = convergence_blackout_ms

        return SimulationOutcome(
            route_info=info, packet_count=packet_count, packet_size=packet_size, random_seed=random_seed,
            delivered_packets=delivered, dropped_packets=packet_count - delivered,
            simulated_duration_ms=last_event_ms, packets=kept,
        )

    # --- metrics ---------------------------------------------------------------
    @staticmethod
    def calculate_throughput_mbps(delivered_bytes: int, duration_ms: float) -> float:
        """Delivered data over simulated time: bits / (ms * 1000) = Mbit/s."""
        if duration_ms <= 0:
            return 0.0
        return delivered_bytes * 8 / (duration_ms * 1000.0)

    def calculate_metrics(self, outcome: SimulationOutcome) -> TrafficMetrics:
        """Derive every reported metric from the outcome; nothing here is random or invented."""
        info = outcome.route_info
        delivered_bytes = outcome.delivered_packets * outcome.packet_size
        return TrafficMetrics(
            packet_count=outcome.packet_count,
            delivered_packets=outcome.delivered_packets,
            dropped_packets=outcome.dropped_packets,
            packet_loss_percentage=round(outcome.dropped_packets / outcome.packet_count * 100.0, 6),
            total_data_transferred_bytes=delivered_bytes,
            path_latency_ms=info.latency_ms,
            hop_count=info.hop_count,
            path_bandwidth_mbps=info.bandwidth_mbps,
            throughput_mbps=round(self.calculate_throughput_mbps(delivered_bytes, outcome.simulated_duration_ms), 6),
            simulated_duration_ms=round(outcome.simulated_duration_ms, 6),
        )
