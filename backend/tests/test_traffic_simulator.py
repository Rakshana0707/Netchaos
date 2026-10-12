"""Unit tests for the pure simulator: no database, no HTTP."""
import networkx as nx
import pytest

from app.enums import PacketStatus
from app.simulation.traffic_simulator import RouteUnavailableError, TrafficSimulator


def make_graph(edges, nodes=()):
    """edges: (u, v, bandwidth, latency[, packet_loss[, status]])"""
    g = nx.Graph()
    for n in nodes:
        g.add_node(n, status="active")
    for i, e in enumerate(edges):
        u, v, bw, lat = e[:4]
        loss = e[4] if len(e) > 4 else 0
        status = e[5] if len(e) > 5 else "active"
        for n in (u, v):
            if n not in g:
                g.add_node(n, status="active")
        g.add_edge(u, v, link_id=f"link_{i + 1:03d}", bandwidth=bw, latency=lat, packet_loss=loss, status=status)
    return g


@pytest.fixture()
def chain():
    # A -10ms/100Mbps- B -20ms/50Mbps- C -30ms/80Mbps- D
    return make_graph([("A", "B", 100, 10), ("B", "C", 50, 20), ("C", "D", 80, 30)])


def test_route_is_shortest_path(chain):
    assert TrafficSimulator(chain).calculate_route("A", "D") == ["A", "B", "C", "D"]


def test_route_prefers_fewer_hops():
    g = make_graph([("A", "B", 100, 1), ("B", "C", 100, 1), ("C", "D", 100, 1), ("A", "D", 100, 500)])
    assert TrafficSimulator(g).calculate_route("A", "D") == ["A", "D"]


def test_latency_is_sum_of_link_latencies(chain):
    assert TrafficSimulator(chain).calculate_route_latency(["A", "B", "C", "D"]) == 60


def test_latency_is_read_from_the_graph_not_hardcoded(chain):
    chain["B"]["C"]["latency"] = 99
    assert TrafficSimulator(chain).calculate_route_latency(["A", "B", "C", "D"]) == 10 + 99 + 30


def test_hop_count_is_links_not_nodes(chain):
    info = TrafficSimulator(chain).analyze_route("A", "D")
    assert info.hop_count == 3 and len(info.route) == 4


def test_path_bandwidth_is_bottleneck(chain):
    assert TrafficSimulator(chain).calculate_path_bandwidth(["A", "B", "C", "D"]) == 50


def test_analyze_route_reports_everything(chain):
    info = TrafficSimulator(chain).analyze_route("A", "D")
    assert (info.available, info.latency_ms, info.bandwidth_mbps, info.reason) == (True, 60, 50, None)


def test_no_route_is_reported_not_raised_by_analyze():
    g = make_graph([("A", "B", 100, 1)], nodes=["Z"])
    info = TrafficSimulator(g).analyze_route("A", "Z")
    assert info.available is False and info.route == []
    assert info.reason == "No route available between source and destination"
    with pytest.raises(RouteUnavailableError):
        TrafficSimulator(g).simulate_traffic("A", "Z", 10, 1000, 1)


def test_inactive_link_is_not_used_and_there_is_no_rerouting():
    g = make_graph([("A", "B", 100, 1), ("B", "C", 100, 1, 0, "down"), ("A", "C", 100, 1)])
    # the direct A-C link is fine, so it is used
    assert TrafficSimulator(g).calculate_route("A", "C") == ["A", "C"]
    # with only the 'down' link between B and C, C is unreachable from B
    g2 = make_graph([("A", "B", 100, 1), ("B", "C", 100, 1, 0, "down")])
    assert TrafficSimulator(g2).analyze_route("A", "C").available is False


def test_inactive_endpoint_is_unavailable():
    g = make_graph([("A", "B", 100, 1)])
    g.nodes["B"]["status"] = "down"
    info = TrafficSimulator(g).analyze_route("A", "B")
    # Module 3: a route that contains a failed node is reported as unavailable (spec wording).
    assert not info.available and info.reason == "Current route contains failed node"
    assert info.failed_nodes == ("B",) and info.blocked_route == ["A", "B"]


def test_failed_node_on_route_is_not_routed_around_even_if_a_detour_exists():
    # A-B-D is the shortest route; A-C-E-D also exists, but there must be NO rerouting.
    edges = [("A", "B", 100, 1), ("B", "D", 100, 1), ("A", "C", 100, 1), ("C", "E", 100, 1), ("E", "D", 100, 1)]
    g = make_graph(edges)
    g.nodes["B"]["status"] = "failed"
    info = TrafficSimulator(g).analyze_route("A", "D")
    assert info.available is False and info.reason == "Current route contains failed node"
    assert info.blocked_route == ["A", "B", "D"]
    with pytest.raises(RouteUnavailableError, match="failed node"):
        TrafficSimulator(g).simulate_traffic("A", "D", 10, 1000, 1)


def test_failed_link_on_route_is_not_routed_around_even_if_a_detour_exists():
    edges = [("A", "B", 100, 1), ("B", "D", 100, 1, 0, "failed"), ("A", "C", 100, 1), ("C", "E", 100, 1), ("E", "D", 100, 1)]
    info = TrafficSimulator(make_graph(edges)).analyze_route("A", "D")
    assert info.available is False and info.reason == "Current route contains failed link"
    assert info.failed_links == ("link_002",)


def test_failure_off_the_route_does_not_matter():
    edges = [("A", "B", 100, 1), ("B", "D", 100, 1), ("A", "C", 100, 1, 0, "failed")]
    g = make_graph(edges)
    assert TrafficSimulator(g).analyze_route("A", "D").available is True


def test_tie_break_is_deterministic_regardless_of_insertion_order():
    edges = [("A", "B", 100, 1), ("B", "D", 100, 1), ("A", "C", 100, 1), ("C", "D", 100, 1)]
    forward = TrafficSimulator(make_graph(edges)).calculate_route("A", "D")
    backward = TrafficSimulator(make_graph(list(reversed(edges)))).calculate_route("A", "D")
    assert forward == backward == ["A", "B", "D"]


def test_snapshot_is_isolated_from_later_graph_changes(chain):
    sim = TrafficSimulator(chain)
    chain["B"]["C"]["latency"] = 1000
    chain.remove_edge("C", "D")
    assert sim.calculate_route_latency(["A", "B", "C", "D"]) == 60


# --- packet loss ------------------------------------------------------------------------------
def lossy():
    return make_graph([("A", "B", 100, 10, 0), ("B", "C", 100, 10, 10), ("C", "D", 100, 10, 0)])


def run(graph, seed, count=1000, size=1000, **kw):
    sim = TrafficSimulator(graph)
    return sim, sim.simulate_traffic("A", "D", count, size, seed, **kw)


def test_same_seed_gives_identical_packet_fates():
    _, a = run(lossy(), 42, keep_packets=True)
    _, b = run(lossy(), 42, keep_packets=True)
    assert [(p.status, p.completed_at_ms) for p in a.packets] == [(p.status, p.completed_at_ms) for p in b.packets]
    assert a.dropped_packets == b.dropped_packets


def test_different_seed_gives_different_losses():
    assert run(lossy(), 1)[1].dropped_packets != run(lossy(), 2)[1].dropped_packets


def test_loss_rate_is_close_to_link_probability():
    _, out = run(lossy(), 42, count=10_000)
    assert 0.09 < out.dropped_packets / 10_000 < 0.11  # 10% on one link


def test_packets_are_dropped_on_the_lossy_link_only():
    _, out = run(lossy(), 42, keep_packets=True)
    dropped = [p for p in out.packets if p.status is PacketStatus.DROPPED]
    assert dropped and {p.dropped_at_link_id for p in dropped} == {"link_002"}


def test_loss_compounds_across_links():
    g = make_graph([("A", "B", 100, 1, 10), ("B", "C", 100, 1, 10)])
    sim = TrafficSimulator(g)
    out = sim.simulate_traffic("A", "C", 20_000, 500, 7)
    assert 0.17 < out.dropped_packets / 20_000 < 0.21  # 1 - 0.9*0.9 = 19%


def test_zero_loss_never_drops_and_full_loss_always_drops():
    assert run(make_graph([("A", "D", 100, 1, 0)]), 3)[1].dropped_packets == 0
    assert run(make_graph([("A", "D", 100, 1, 100)]), 3)[1].delivered_packets == 0


# --- timing and throughput -----------------------------------------------------------------------
def test_single_packet_timing_matches_hand_calculation():
    # 1000 bytes = 8000 bits. On 100 Mbps: 0.08 ms; on 50 Mbps: 0.16 ms. Overhead 0.05 per hop.
    g = make_graph([("A", "B", 100, 10), ("B", "C", 50, 20)])
    sim = TrafficSimulator(g)
    out = sim.simulate_traffic("A", "C", 1, 1000, 1, keep_packets=True)
    expected = (0.08 + 10 + 0.05) + (0.16 + 20 + 0.05)
    assert out.simulated_duration_ms == pytest.approx(expected)
    assert out.packets[0].completed_at_ms == pytest.approx(expected)


def test_bottleneck_sets_the_pace_of_the_packet_train():
    g = make_graph([("A", "B", 100, 0), ("B", "C", 10, 0)])
    sim = TrafficSimulator(g, processing_overhead_ms=0)
    n, size = 100, 1250  # 10000 bits: 0.1 ms on 100 Mbps, 1.0 ms on 10 Mbps
    out = sim.simulate_traffic("A", "C", n, size, 1)
    # first packet reaches the slow link at 0.1 ms; then 100 packets take 1 ms each
    assert out.simulated_duration_ms == pytest.approx(0.1 + n * 1.0)


def test_throughput_is_delivered_bits_over_simulated_duration():
    sim, out = run(lossy(), 42, count=500, size=1024)
    m = sim.calculate_metrics(out)
    assert m.throughput_mbps == pytest.approx(out.delivered_packets * 1024 * 8 / (out.simulated_duration_ms * 1000), rel=1e-5)
    assert m.total_data_transferred_bytes == out.delivered_packets * 1024


def test_throughput_never_exceeds_path_bandwidth_and_is_zero_when_nothing_arrives():
    sim, out = run(lossy(), 42, count=2000)
    assert 0 < sim.calculate_metrics(out).throughput_mbps <= 100
    sim, out = run(make_graph([("A", "D", 100, 1, 100)]), 1)
    assert sim.calculate_metrics(out).throughput_mbps == 0


def test_calculate_throughput_formula():
    assert TrafficSimulator.calculate_throughput_mbps(1_000_000, 1000) == pytest.approx(8.0)  # 8 Mbit in 1 s
    assert TrafficSimulator.calculate_throughput_mbps(1000, 0) == 0


def test_metrics_are_internally_consistent():
    sim, out = run(lossy(), 42, count=1000)
    m = sim.calculate_metrics(out)
    assert m.delivered_packets + m.dropped_packets == m.packet_count
    assert m.packet_loss_percentage == pytest.approx(m.dropped_packets / m.packet_count * 100)
    assert (m.hop_count, m.path_latency_ms, m.path_bandwidth_mbps) == (3, 30, 100)


def test_bandwidth_change_is_picked_up_by_the_next_simulation():
    g = make_graph([("A", "B", 100, 5), ("B", "C", 100, 5)])
    fast = TrafficSimulator(g).simulate_traffic("A", "C", 200, 1500, 1).simulated_duration_ms
    g["B"]["C"]["bandwidth"] = 5  # what a future chaos module would do
    slow = TrafficSimulator(g).simulate_traffic("A", "C", 200, 1500, 1).simulated_duration_ms
    assert slow > fast * 5


@pytest.mark.parametrize("count", [100, 1_000, 10_000])
def test_scales_to_10k_packets(count):
    sim, out = run(lossy(), 42, count=count)
    assert out.delivered_packets + out.dropped_packets == count


def test_rejects_bad_arguments(chain):
    with pytest.raises(ValueError):
        TrafficSimulator(chain).simulate_traffic("A", "D", 0, 100, 1)
    with pytest.raises(ValueError):
        TrafficSimulator(chain).simulate_traffic("A", "D", 10, 0, 1)
