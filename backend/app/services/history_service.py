from pymongo.database import Database
from datetime import datetime, timezone
from typing import List

from app.errors import NotFoundError, BadRequestError
from app.schemas.history import (
    ExperimentStatus, ExperimentCreate, ExperimentResponse, EventDetail, 
    ExperimentDetailResponse
)
from app.analysis.performance_analyzer import PerformanceAnalyzer
from app.analysis.impact_analyzer import ImpactAnalyzer
from app.analysis.recovery_analyzer import RecoveryAnalyzer
from app.analysis.comparison_engine import ComparisonEngine
from app.analysis.phase_metrics import compute_phase_metrics
from app.services.ids import next_id

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

class HistoryService:
    def __init__(self, db: Database):
        self.db = db
        self.perf_analyzer = PerformanceAnalyzer()
        self.impact_analyzer = ImpactAnalyzer()
        self.recovery_analyzer = RecoveryAnalyzer()
        self.compare_engine = ComparisonEngine()

    def _next_exp_id(self, network_id: str) -> str:
        return next_id(self.db.experiments, {"network_id": network_id}, f"exp_{network_id[-3:]}_")

    def create_experiment(self, network_id: str, req: ExperimentCreate) -> ExperimentResponse:
        now = _utcnow()
        doc = {
            "id": self._next_exp_id(network_id),
            "network_id": network_id,
            "name": req.name,
            "description": req.description,
            "status": ExperimentStatus.CREATED.value,
            "started_at": now,
            "ended_at": None,
            "baseline_snapshot_id": None,
            "final_snapshot_id": None,
            "phases": {},
            "created_at": now
        }
        self.db.experiments.insert_one(doc)
        doc.pop("_id", None)
        return ExperimentResponse(**doc)
        
    def complete_experiment(self, experiment_id: str) -> ExperimentResponse:
        exp = self.db.experiments.find_one({"id": experiment_id})
        if not exp:
            raise NotFoundError(f"Experiment {experiment_id} not found")
            
        now = _utcnow()
        self.db.experiments.update_one(
            {"id": experiment_id},
            {"$set": {"status": ExperimentStatus.COMPLETED.value, "ended_at": now}}
        )
        exp["status"] = ExperimentStatus.COMPLETED.value
        exp["ended_at"] = now
        exp.pop("_id", None)
        return ExperimentResponse(**exp)

    def mark_failed(self, experiment_id: str) -> None:
        self.db.experiments.update_one(
            {"id": experiment_id}, {"$set": {"status": ExperimentStatus.FAILED.value, "ended_at": _utcnow()}})

    def get_experiments(self, network_id: str, limit: int = 50) -> List[ExperimentResponse]:
        docs = self.db.experiments.find({"network_id": network_id}).sort("created_at", -1).limit(limit)
        return [ExperimentResponse(**d) for d in docs]
        
    PHASE_KEYS = ("baseline_simulation_id", "chaos_simulation_id", "post_recovery_simulation_id",
                  "recovery_id", "detection_id", "chaos_experiment_ids")

    def link_phases(self, experiment_id: str, phases: dict) -> ExperimentResponse:
        """Attach the records that make up an experiment (explicit links, validated against its network)."""
        exp = self.db.experiments.find_one({"id": experiment_id})
        if not exp:
            raise NotFoundError(f"Experiment {experiment_id} not found")
        nid = exp["network_id"]
        unknown = set(phases) - set(self.PHASE_KEYS)
        if unknown:
            raise BadRequestError(f"Unknown phase keys: {sorted(unknown)}", "invalid_phase")
        sources = {"baseline_simulation_id": "traffic_simulations", "chaos_simulation_id": "traffic_simulations",
                   "post_recovery_simulation_id": "traffic_simulations", "recovery_id": "recovery_events",
                   "detection_id": "failure_detections"}
        updates = {}
        for key, value in phases.items():
            if value is None:
                continue
            ids = value if key == "chaos_experiment_ids" else [value]
            collection = "chaos_experiments" if key == "chaos_experiment_ids" else sources[key]
            for rid in ids:
                if not self.db[collection].find_one({"id": rid, "network_id": nid}):
                    raise NotFoundError(f"{key} '{rid}' not found in network '{nid}'", "phase_record_not_found")
            updates[f"phases.{key}"] = list(ids) if key == "chaos_experiment_ids" else value
        if updates:
            self.db.experiments.update_one({"id": experiment_id}, {"$set": updates})
        return ExperimentResponse(**self._without_oid(self.db.experiments.find_one({"id": experiment_id})))

    @staticmethod
    def _without_oid(doc: dict) -> dict:
        doc = dict(doc)
        doc.pop("_id", None)
        return doc

    def load_phase_records(self, exp: dict) -> dict:
        """Fetch the explicitly linked records of an experiment (missing links -> None / empty)."""
        nid, ph = exp["network_id"], exp.get("phases") or {}

        def one(collection: str, key: str):
            return self.db[collection].find_one({"id": ph[key], "network_id": nid}) if ph.get(key) else None

        chaos = list(self.db.chaos_experiments.find(
            {"network_id": nid, "id": {"$in": ph.get("chaos_experiment_ids", [])}}).sort("created_at", 1))
        return {
            "baseline": one("traffic_simulations", "baseline_simulation_id"),
            "chaos_sim": one("traffic_simulations", "chaos_simulation_id"),
            "post": one("traffic_simulations", "post_recovery_simulation_id"),
            "recovery": one("recovery_events", "recovery_id"),
            "detection": one("failure_detections", "detection_id"),
            "chaos": chaos,
        }

    def phase_metrics(self, exp: dict) -> tuple[dict, dict]:
        records = self.load_phase_records(exp)
        metrics = compute_phase_metrics(records["baseline"], records["chaos_sim"], records["recovery"], records["post"])
        return metrics, records

    def get_experiment_detail(self, experiment_id: str) -> ExperimentDetailResponse:
        exp = self.db.experiments.find_one({"id": experiment_id})
        if not exp:
            raise NotFoundError(f"Experiment {experiment_id} not found")
        nid = exp["network_id"]
        metrics, rec = self.phase_metrics(exp)
        linked = bool(exp.get("phases"))
        start = exp["started_at"]
        end = exp["ended_at"] or _utcnow()

        def window(collection: str, field: str) -> list:
            return list(self.db[collection].find({"network_id": nid, field: {"$gte": start, "$lte": end}}).sort(field, 1))

        snaps = window("monitoring_snapshots", "timestamp")
        chaos = rec["chaos"] if linked else window("chaos_experiments", "created_at")
        recoveries = [rec["recovery"]] if rec["recovery"] else ([] if linked else window("recovery_events", "created_at"))
        detections = [rec["detection"]] if rec["detection"] else ([] if linked else window("failure_detections", "detected_at"))

        timeline = [EventDetail(timestamp=start, event_type="EXPERIMENT_STARTED", description=f"Experiment '{exp['name']}' started", source_module="history", severity="info")]
        for c in chaos:
            timeline.append(EventDetail(timestamp=c["created_at"], event_type="CHAOS_INJECTED", description=f"Chaos injected: {c.get('scenario_type', 'unknown')}", source_module="chaos", severity="critical"))
        for d in detections:
            timeline.append(EventDetail(timestamp=d["detected_at"], event_type="FAILURE_DETECTED", description=f"Failure detected: {d.get('overall_status')} ({d.get('failed_nodes', 0)} nodes, {d.get('failed_links', 0)} links failed)", source_module="failure_detection", severity="high"))
        for r in recoveries:
            timeline.append(EventDetail(timestamp=r["created_at"], event_type="RECOVERY_ATTEMPTED", description=f"Recovery {r.get('recovery_status')}", source_module="recovery", severity="medium"))
        for sn in snaps:
            timeline.append(EventDetail(timestamp=sn["timestamp"], event_type="MONITORING_SNAPSHOT", description=f"Snapshot captured: {sn['health_status']}", source_module="monitoring", severity="info"))
        if exp["status"] == ExperimentStatus.COMPLETED.value:
            timeline.append(EventDetail(timestamp=end, event_type="EXPERIMENT_COMPLETED", description="Experiment finished", source_module="history", severity="info"))
        timeline.sort(key=lambda e: e.timestamp)

        events = list(self.db.chaos_events.find({"network_id": nid, "experiment_id": {"$in": [c["id"] for c in chaos]}})) if chaos else []
        partitions = max((rec["detection"] or {}).get("connected_components", 1) - 1, 0)
        return ExperimentDetailResponse(
            experiment=ExperimentResponse(**self._without_oid(exp)),
            timeline=timeline,
            performance_analysis=(self.perf_analyzer.analyze_phases(metrics) if linked
                                  else self.perf_analyzer.analyze_snapshots(snaps)),
            failure_impacts=self.impact_analyzer.analyze(chaos, events, metrics, partitions) if linked else [],
            recovery_analysis=self.recovery_analyzer.analyze(recoveries),
            metrics=metrics,
        )

    def compare(self, experiment_ids: List[str]) -> List[dict]:
        details = []
        for eid in experiment_ids:
            try:
                details.append(self.get_experiment_detail(eid).model_dump())
            except NotFoundError:
                pass
        return self.compare_engine.compare_experiments(details)
