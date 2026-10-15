"""Business logic for chaos injection using MongoDB."""
from dataclasses import dataclass
from datetime import datetime, timezone

from pymongo.database import Database

from app.chaos.state import effective_state, snapshot
from app.enums import ChaosStatus, ElementStatus, ScenarioType, TargetType
from app.errors import ConflictError, NotFoundError
from app.graph import GraphError, GraphManager
from app.schemas.chaos import (
    FAILURE_SCENARIOS, ActiveChaosResponse, ActiveExperiment, ChaosEventResponse, EventSpec,
    ExperimentResponse, ExperimentSpec, HistoryItem, HistoryResponse, ResetResponse, RestoredTarget,
    RevertResponse,
)
from app.services.ids import max_suffix
from app.services.topology_service import TopologyService

_TITLES = {
    ScenarioType.ROUTER_FAILURE: "Router Failure",
    ScenarioType.LINK_FAILURE: "Link Failure",
    ScenarioType.PACKET_LOSS: "Packet Loss",
    ScenarioType.LATENCY: "Latency Injection",
    ScenarioType.BANDWIDTH_REDUCTION: "Bandwidth Reduction",
    ScenarioType.CONGESTION: "Network Congestion",
    ScenarioType.MULTI_FAILURE: "Multi-failure",
}
_FAILED = ElementStatus.FAILED.value

def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)

@dataclass
class _Labels:
    nodes: dict[str, str]
    links: dict[str, str]

    def of(self, target_type: str, target_id: str) -> str:
        if target_type == TargetType.NODE.value:
            return self.nodes.get(target_id, target_id)
        if target_type == TargetType.LINK.value:
            return self.links.get(target_id, target_id)
        return "network"

@dataclass
class _Changes:
    nodes: dict[str, dict]
    links: dict[str, dict]

    @classmethod
    def empty(cls) -> "_Changes":
        return cls({}, {})

    def record(self, target_type: str, target_id: str, state: dict) -> None:
        (self.nodes if target_type == TargetType.NODE.value else self.links)[target_id] = state

class ChaosService:
    def __init__(self, db: Database, graphs: GraphManager) -> None:
        self.db = db
        self.graphs = graphs
        self.topology = TopologyService(db, graphs)

    def apply(self, network_id: str, spec: ExperimentSpec) -> ExperimentResponse:
        changes = _Changes.empty()
        self.topology.get_network(network_id, lock=True)
        labels = self._labels(network_id)
        now = utc_now()
        
        exp_seq = max_suffix(self.db.chaos_experiments, {"network_id": network_id}, "chaos_") + 1

        experiment = {
            "id": f"chaos_{exp_seq:03d}",
            "network_id": network_id,
            "name": (spec.name or self._default_name(spec, labels))[:100],
            "description": spec.description,
            "scenario_type": spec.scenario.value,
            "status": ChaosStatus.ACTIVE.value,
            "started_at": now,
            "created_at": now
        }
        
        evt_seq = max_suffix(self.db.chaos_events, {"network_id": network_id}, "evt_")

        events_to_insert = []
        for event_spec in spec.events:
            evt_seq += 1
            evt = self._apply_event(experiment, event_spec, changes, evt_seq, now)
            events_to_insert.append(evt)
            
        self.db.chaos_experiments.insert_one(experiment)
        if events_to_insert:
            self.db.chaos_events.insert_many(events_to_insert)
            
        for key, state in changes.nodes.items():
            self._write_row(TargetType.NODE, key, network_id, state)
        for key, state in changes.links.items():
            self._write_row(TargetType.LINK, key, network_id, state)
            
        self._sync_graph(network_id, changes)
        return self._experiment_response(experiment, events_to_insert, self._labels(network_id))

    def _apply_event(self, experiment: dict, spec: EventSpec, changes: _Changes, seq: int, now: datetime) -> dict:
        network_id = experiment["network_id"]
        row = self._target_row(network_id, spec.target_type, spec.target_id)
        current = snapshot(spec.target_type, row)
        pending = (changes.nodes if spec.target_type is TargetType.NODE else changes.links).get(spec.target_id)
        if pending is not None:
            current = pending
            
        if spec.scenario in FAILURE_SCENARIOS and current["status"] == _FAILED:
            kind = "Router" if spec.target_type is TargetType.NODE else "Link"
            raise ConflictError(f"{kind} '{spec.target_id}' has already failed; revert its experiment first", f"{spec.target_type.value}_already_failed")
            
        active = self._active_events(network_id, spec.target_type.value, spec.target_id)
        baseline = dict(active[0]["previous_state"]) if active else current
        
        event = {
            "id": f"evt_{seq:03d}",
            "network_id": network_id,
            "experiment_id": experiment["id"],
            "scenario_type": spec.scenario.value,
            "target_type": spec.target_type.value,
            "target_id": spec.target_id,
            "parameters": dict(spec.parameters),
            "previous_state": baseline,
            "status": ChaosStatus.ACTIVE.value,
            "started_at": now,
            "created_at": now
        }
        
        layers = [(e["scenario_type"], e["parameters"]) for e in active] + [(event["scenario_type"], event["parameters"])]
        state = effective_state(baseline, layers)
        event["new_state"] = state
        changes.record(spec.target_type.value, spec.target_id, state)
        return event

    def revert(self, network_id: str, experiment_id: str) -> RevertResponse:
        changes = _Changes.empty()
        self.topology.get_network(network_id, lock=True)
        experiment = self._get_experiment(network_id, experiment_id)
        already = experiment["status"] != ChaosStatus.ACTIVE.value
        reverted_events = self._revert_experiments(network_id, [experiment], changes)
        self._sync_graph(network_id, changes)
        labels = self._labels(network_id)
        restored = [
            RestoredTarget(target_type=t, target_id=i, target_label=labels.of(t.value, i), state=state)
            for t, bucket in ((TargetType.NODE, changes.nodes), (TargetType.LINK, changes.links))
            for i, state in sorted(bucket.items())
        ]
        return RevertResponse(
            network_id=network_id, experiment_id=experiment_id, status=ChaosStatus(experiment["status"]),
            already_reverted=already, reverted_events=reverted_events, restored=restored,
        )

    def reset(self, network_id: str, clear_history: bool = True) -> ResetResponse:
        changes = _Changes.empty()
        self.topology.get_network(network_id, lock=True)
        active = self._experiments(network_id, only_active=True)
        self._revert_experiments(network_id, active, changes)
        self._sync_graph(network_id, changes)
        if clear_history:
            self.db.chaos_experiments.delete_many({"network_id": network_id})
            self.db.chaos_events.delete_many({"network_id": network_id})
            self.db.recovery_events.delete_many({"network_id": network_id})
            self.db.failure_detections.delete_many({"network_id": network_id})
            self.db.traffic_simulations.delete_many({"network_id": network_id})
            self.db.monitoring_snapshots.delete_many({"network_id": network_id})
        return ResetResponse(network_id=network_id, reverted_experiments=len(active))

    def _revert_experiments(self, network_id: str, experiments: list[dict], changes: _Changes) -> int:
        now = utc_now()
        baselines: dict[tuple[str, str], dict] = {}
        reverted_events = 0
        
        for experiment in experiments:
            if experiment["status"] != ChaosStatus.ACTIVE.value:
                continue
            
            events = self._events_of(experiment)
            for event in events:
                if event["status"] != ChaosStatus.ACTIVE.value:
                    continue
                self.db.chaos_events.update_one(
                    {"id": event["id"], "network_id": network_id},
                    {"$set": {"status": ChaosStatus.REVERTED.value, "ended_at": now}}
                )
                baselines.setdefault((event["target_type"], event["target_id"]), dict(event["previous_state"]))
                reverted_events += 1
            
            self.db.chaos_experiments.update_one(
                {"id": experiment["id"], "network_id": network_id},
                {"$set": {"status": ChaosStatus.REVERTED.value, "ended_at": now}}
            )
            experiment["status"] = ChaosStatus.REVERTED.value

        for (target_type, target_id), baseline in baselines.items():
            row = self._find_target_row(network_id, TargetType(target_type), target_id)
            if row is None:
                continue
            remaining = self._active_events(network_id, target_type, target_id)
            state = effective_state(baseline, [(e["scenario_type"], e["parameters"]) for e in remaining])
            self._write_row(TargetType(target_type), target_id, network_id, state)
            changes.record(target_type, target_id, state)
            
        return reverted_events

    def get_experiment(self, network_id: str, experiment_id: str) -> ExperimentResponse:
        self.topology.get_network(network_id)
        experiment = self._get_experiment(network_id, experiment_id)
        return self._experiment_response(experiment, self._events_of(experiment), self._labels(network_id))

    def active(self, network_id: str) -> ActiveChaosResponse:
        self.topology.get_network(network_id)
        labels = self._labels(network_id)
        items = []
        for experiment in self._experiments(network_id, only_active=True):
            full = self._experiment_response(experiment, self._events_of(experiment), labels)
            live = [e for e in full.events if e.status is ChaosStatus.ACTIVE]
            flat = dict(live[0].parameters) if len(full.events) == 1 else {}
            items.append(ActiveExperiment(
                experiment_id=full.experiment_id, name=full.name, scenario=full.scenario, target=full.target,
                target_label=full.target_label, status=full.status, created_at=full.created_at,
                started_at=full.started_at, events=live, **flat,
            ))
        return ActiveChaosResponse(network_id=network_id, active_experiments=items)

    def history(self, network_id: str) -> HistoryResponse:
        self.topology.get_network(network_id)
        labels = self._labels(network_id)
        items = []
        # newest first
        for experiment in self.db.chaos_experiments.find({"network_id": network_id}).sort("id", -1):
            full = self._experiment_response(experiment, self._events_of(experiment), labels)
            items.append(HistoryItem(
                experiment_id=full.experiment_id, name=full.name, scenario=full.scenario, target=full.target,
                target_label=full.target_label, status=full.status, event_count=len(full.events),
                created_at=full.created_at, ended_at=full.ended_at,
            ))
        return HistoryResponse(network_id=network_id, experiments=items)

    def _experiments(self, network_id: str, only_active: bool = False) -> list[dict]:
        query = {"network_id": network_id}
        if only_active:
            query["status"] = ChaosStatus.ACTIVE.value
        return list(self.db.chaos_experiments.find(query).sort("id", 1))

    def _get_experiment(self, network_id: str, experiment_id: str) -> dict:
        experiment = self.db.chaos_experiments.find_one({"id": experiment_id, "network_id": network_id})
        if not experiment:
            raise NotFoundError(f"Chaos experiment '{experiment_id}' not found in network '{network_id}'", "experiment_not_found")
        return experiment

    def _events_of(self, experiment: dict) -> list[dict]:
        return list(self.db.chaos_events.find({
            "network_id": experiment["network_id"], "experiment_id": experiment["id"]
        }).sort("id", 1))

    def _active_events(self, network_id: str, target_type: str, target_id: str) -> list[dict]:
        return list(self.db.chaos_events.find({
            "network_id": network_id, "target_type": target_type,
            "target_id": target_id, "status": ChaosStatus.ACTIVE.value,
        }).sort("id", 1))

    def _find_target_row(self, network_id: str, target_type: TargetType, target_id: str) -> dict | None:
        collection = self.db.nodes if target_type is TargetType.NODE else self.db.links
        return collection.find_one({"id": target_id, "network_id": network_id})

    def _target_row(self, network_id: str, target_type: TargetType, target_id: str) -> dict:
        row = self._find_target_row(network_id, target_type, target_id)
        if row is None:
            kind = "Node" if target_type is TargetType.NODE else "Link"
            raise NotFoundError(f"{kind} '{target_id}' not found in network '{network_id}'", f"{kind.lower()}_not_found")
        return row

    def _write_row(self, target_type: TargetType, target_id: str, network_id: str, state: dict) -> None:
        collection = self.db.nodes if target_type is TargetType.NODE else self.db.links
        collection.update_one({"id": target_id, "network_id": network_id}, {"$set": state})

    def _sync_graph(self, network_id: str, changes: _Changes) -> None:
        try:
            updates = {
                TargetType.NODE: self._committed(network_id, TargetType.NODE, changes.nodes),
                TargetType.LINK: self._committed(network_id, TargetType.LINK, changes.links),
            }
            self.graphs.update_elements(network_id, updates[TargetType.NODE], updates[TargetType.LINK])
        except GraphError:
            self.topology.reload_graph(network_id)

    def _committed(self, network_id: str, target_type: TargetType, targets: dict[str, dict]) -> dict[str, dict]:
        states = {}
        for target_id in targets:
            row = self._find_target_row(network_id, target_type, target_id)
            if row is not None:
                class PseudoRow:
                    def __init__(self, d):
                        for k, v in d.items():
                            setattr(self, k, v)
                states[target_id] = snapshot(target_type, PseudoRow(row))
        return states

    def _labels(self, network_id: str) -> _Labels:
        nodes = {n["id"]: n["name"] for n in self.db.nodes.find({"network_id": network_id})}
        links = {
            l["id"]: f"{nodes.get(l['source_node_id'], l['source_node_id'])} ↔ {nodes.get(l['destination_node_id'], l['destination_node_id'])}"
            for l in self.db.links.find({"network_id": network_id})
        }
        return _Labels(nodes, links)

    @staticmethod
    def _default_name(spec: ExperimentSpec, labels: _Labels) -> str:
        if spec.scenario is ScenarioType.MULTI_FAILURE:
            return f"Multi-failure ({len(spec.events)} events)"
        event = spec.events[0]
        return f"{_TITLES[spec.scenario]}: {labels.of(event.target_type.value, event.target_id)}"

    @staticmethod
    def _experiment_response(experiment: dict, events: list[dict], labels: _Labels) -> ExperimentResponse:
        event_items = [
            ChaosEventResponse(
                event_id=e["id"], scenario=e["scenario_type"], target_type=e["target_type"], target_id=e["target_id"],
                target_label=labels.of(e["target_type"], e["target_id"]), parameters=e["parameters"],
                previous_state=e["previous_state"], new_state=e["new_state"], status=e["status"],
                started_at=e["started_at"], ended_at=e.get("ended_at"),
            )
            for e in events
        ]
        if experiment["scenario_type"] == ScenarioType.MULTI_FAILURE.value:
            target, target_label = TargetType.NETWORK.value, f"{len(events)} targets"
        else:
            target = events[0]["target_id"]
            target_label = labels.of(events[0]["target_type"], target)
        return ExperimentResponse(
            experiment_id=experiment["id"], network_id=experiment["network_id"], name=experiment["name"],
            description=experiment.get("description"), scenario=experiment["scenario_type"], target=target,
            target_label=target_label, status=experiment["status"], created_at=experiment.get("created_at") or experiment["started_at"],
            started_at=experiment.get("started_at"), ended_at=experiment.get("ended_at"), events=event_items,
        )
