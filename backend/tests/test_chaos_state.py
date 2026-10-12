"""Pure-logic tests for the chaos state maths (no database, no HTTP)."""
import pytest

from app.chaos.state import apply_event, effective_state, snapshot

LINK = {"status": "active", "bandwidth": 100.0, "latency": 20.0, "packet_loss": 0.0}


def test_failure_sets_status_only():
    assert apply_event(LINK, "link_failure", {}) == {**LINK, "status": "failed"}
    assert apply_event({"status": "active"}, "router_failure", {}) == {"status": "failed"}


@pytest.mark.parametrize("scenario, params, field, value", [
    ("packet_loss", {"packet_loss": 30}, "packet_loss", 30.0),
    ("latency", {"latency": 150}, "latency", 150.0),
    ("bandwidth_reduction", {"bandwidth": 20}, "bandwidth", 20.0),
])
def test_absolute_operators_set_one_field(scenario, params, field, value):
    out = apply_event(LINK, scenario, params)
    assert out == {**LINK, field: value}


def test_congestion_example_from_the_spec():
    out = apply_event(LINK, "congestion", {"latency_increase": 50, "bandwidth_reduction_percent": 40, "packet_loss": 10})
    assert (out["bandwidth"], out["latency"], out["packet_loss"]) == (60.0, 70.0, 10.0)


def test_congestion_caps_loss_at_100_and_is_deterministic():
    params = {"latency_increase": 0.1, "bandwidth_reduction_percent": 33.3, "packet_loss": 95}
    once = apply_event({**LINK, "packet_loss": 20.0}, "congestion", params)
    assert once["packet_loss"] == 100.0
    assert apply_event({**LINK, "packet_loss": 20.0}, "congestion", params) == once


def test_input_is_never_mutated():
    before = dict(LINK)
    apply_event(LINK, "latency", {"latency": 1})
    effective_state(LINK, [("link_failure", {})])
    assert LINK == before


def test_layers_fold_oldest_first_and_latest_absolute_wins():
    layers = [("latency", {"latency": 100}), ("latency", {"latency": 200})]
    assert effective_state(LINK, layers)["latency"] == 200
    assert effective_state(LINK, layers[:1])["latency"] == 100
    assert effective_state(LINK, [])  == LINK


def test_relative_layer_stacks_on_the_layers_below_it():
    with_latency = effective_state(LINK, [("latency", {"latency": 100}), ("congestion", {"latency_increase": 50})])
    assert with_latency["latency"] == 150
    # drop the absolute layer and the congestion applies to the baseline instead
    assert effective_state(LINK, [("congestion", {"latency_increase": 50})])["latency"] == 70


def test_multi_failure_is_not_an_operator():
    with pytest.raises(ValueError):
        apply_event(LINK, "multi_failure", {})


def test_snapshot_only_takes_state_fields():
    assert snapshot("node", {"status": "active", "name": "x"}) == {"status": "active"}
    assert set(snapshot("link", {**LINK, "id": "link_001"})) == set(LINK)
