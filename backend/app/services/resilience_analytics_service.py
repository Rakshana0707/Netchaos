"""Resilience analytics computed from the explicitly linked lifecycle records of each experiment.

All figures are derived from *simulated* traffic and are internal project indicators, not measurements of
a real network. An experiment whose baseline or chaos-phase simulation is missing is reported with
``data_complete = False`` and ``None`` metrics; it is excluded from network aggregates instead of being
filled with defaults.
"""
from pymongo.database import Database
from typing import List, Optional

from app.analysis.phase_metrics import interpret_resilience, resilience_score
from app.errors import NotFoundError
from app.schemas.analytics import (
    AnalyticsSummaryResponse, FailureRanking, ExperimentAnalytics,
    AnalyticsComparisonResponse, RouteResilienceMetrics, ResearchReport,
    ExperimentConfigurationExport, CompareRequest,
)
from app.schemas.history import ExperimentStatus
from app.services.history_service import HistoryService

DISCLAIMER = ("All values come from the NetChaos simulator (simulated latency, loss and throughput; recovery "
              "time is simulator wall-clock). Scores are internal indicators, not industry benchmarks.")


def _mean(values: list) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


class ResilienceAnalyticsService:
    def __init__(self, db: Database):
        self.db = db
        self.history_service = HistoryService(db)

    # ------------------------------------------------------------------ per experiment
    def _load(self, experiment_id: str):
        exp = self.db.experiments.find_one({"id": experiment_id})
        if not exp:
            raise NotFoundError(f"Experiment {experiment_id} not found")
        metrics, records = self.history_service.phase_metrics(exp)
        return exp, metrics, records

    @staticmethod
    def _failure_type(records: dict) -> str:
        return records["chaos"][0].get("scenario_type", "unknown") if records["chaos"] else "unknown"

    def get_experiment_analytics(self, experiment_id: str) -> ExperimentAnalytics:
        _, m, rec = self._load(experiment_id)
        b, c, p = m["phases"]["baseline"], m["phases"]["chaos"], m["phases"]["post_recovery"]
        recovery = rec["recovery"] or {}

        def pick(view, key):
            return None if view is None else view[key]

        return ExperimentAnalytics(
            experiment_id=experiment_id,
            failure_type=self._failure_type(rec),
            impact_score=m["impact_score"],
            connectivity=m["connectivity_preservation"],
            latency_degradation=m["latency_degradation_percent"],
            packet_loss_degradation=m["packet_loss_increase_points"],
            throughput_degradation=m["throughput_degradation_percent"],
            recovery_time=m["recovery_time_seconds"],
            recovery_effectiveness=m["recovery_effectiveness_percent"],
            route_changed=bool(recovery.get("route_changed", False)),
            recoverable=m["recoverable"],
            baseline_latency=pick(b, "latency_ms"), chaos_latency=pick(c, "latency_ms"),
            recovery_latency=pick(p, "latency_ms"),
            baseline_throughput=pick(b, "throughput_mbps"), chaos_throughput=pick(c, "throughput_mbps"),
            recovery_throughput=pick(p, "throughput_mbps"),
            baseline_packet_loss=pick(b, "packet_loss_percent"), chaos_packet_loss=pick(c, "packet_loss_percent"),
            recovery_packet_loss=pick(p, "packet_loss_percent"),
            recovery_status=m["recovery_status"],
            post_recovery_latency_degradation=m["post_recovery_latency_degradation_percent"],
            data_complete=m["data_complete"],
            missing=m["missing"],
        )

    def _completed_analytics(self, network_id: str) -> List[ExperimentAnalytics]:
        """Analytics of completed experiments that have enough data (baseline + chaos phase) to be scored."""
        exps = self.db.experiments.find({"network_id": network_id, "status": ExperimentStatus.COMPLETED.value})
        out = []
        for e in exps:
            a = self.get_experiment_analytics(e["id"])
            if a.impact_score is not None:
                out.append(a)
        return out

    # ------------------------------------------------------------------ network level
    def get_network_analytics_summary(self, network_id: str) -> AnalyticsSummaryResponse:
        analyzed = self._completed_analytics(network_id)
        if not analyzed:
            return AnalyticsSummaryResponse(
                network_id=network_id, experiments_analyzed=0, successful_recoveries=0, failed_recoveries=0)
        succ = sum(1 for a in analyzed if a.recoverable)
        avg_conn = _mean([a.connectivity for a in analyzed])
        recoverability = succ / len(analyzed) * 100.0
        return AnalyticsSummaryResponse(
            network_id=network_id,
            experiments_analyzed=len(analyzed),
            successful_recoveries=succ,
            failed_recoveries=len(analyzed) - succ,
            average_recovery_time=_mean([a.recovery_time for a in analyzed]),
            average_impact_score=_mean([a.impact_score for a in analyzed]),
            average_connectivity_preservation=avg_conn,
            average_recovery_effectiveness=_mean([a.recovery_effectiveness for a in analyzed]),
            resilience_score=resilience_score(avg_conn or 0.0, recoverability),
        )

    def compare_experiments(self, req: CompareRequest) -> AnalyticsComparisonResponse:
        analyzed = []
        for eid in req.experiment_ids:
            try:
                analyzed.append(self.get_experiment_analytics(eid))
            except NotFoundError:
                pass  # unknown ids are skipped
        return AnalyticsComparisonResponse(
            experiments=analyzed,
            summary_message=f"Compared {len(analyzed)} of {len(req.experiment_ids)} requested experiments.")

    @staticmethod
    def _severity(a: ExperimentAnalytics) -> str:
        if not a.recoverable:
            return "critical"
        if (a.impact_score or 0) >= 0.5:
            return "high"
        return "medium" if (a.impact_score or 0) >= 0.2 else "low"

    def get_failure_ranking(self, network_id: str) -> List[FailureRanking]:
        analyzed = sorted(self._completed_analytics(network_id), key=lambda a: a.impact_score, reverse=True)
        ranking = []
        for i, a in enumerate(analyzed, 1):
            impacts = self.history_service.get_experiment_detail(a.experiment_id).failure_impacts
            ranking.append(FailureRanking(
                rank=i, experiment_id=a.experiment_id, failure_type=a.failure_type,
                severity=self._severity(a), impact_score=a.impact_score,
                affected_nodes=sum(x.affected_nodes for x in impacts),
                affected_links=sum(x.affected_links for x in impacts),
                affected_traffic=max((x.affected_traffic for x in impacts), default=0),
                connectivity_preservation=a.connectivity,
                latency_degradation=a.latency_degradation,
                packet_loss_degradation=a.packet_loss_degradation,
                throughput_degradation=a.throughput_degradation,
                recovery_time=a.recovery_time, recoverable=a.recoverable))
        return ranking

    # ------------------------------------------------------------------ report / export
    def generate_experiment_report(self, experiment_id: str) -> ResearchReport:
        exp, m, rec = self._load(experiment_id)
        a = self.get_experiment_analytics(experiment_id)
        recovery = rec["recovery"]
        scored = a.impact_score is not None
        score = resilience_score(a.connectivity or 0.0, 100.0 if a.recoverable else 0.0) if scored else None

        route = None
        if recovery and recovery.get("recovery_status") == "RECOVERED":
            o, r = recovery.get("original_route") or [], recovery.get("recovered_route") or []
            ol, rl = recovery.get("original_latency"), recovery.get("recovered_latency")
            ob, rb = recovery.get("original_bandwidth"), recovery.get("recovered_bandwidth")
            if None not in (ol, rl, ob, rb):
                route = RouteResilienceMetrics(
                    original_hop_count=max(len(o) - 1, 0), recovered_hop_count=max(len(r) - 1, 0),
                    hop_count_increase=len(r) - len(o), original_latency=ol, recovered_latency=rl,
                    latency_increase=rl - ol, original_bandwidth=ob, recovered_bandwidth=rb,
                    bandwidth_reduction=ob - rb, route_changed=bool(recovery.get("route_changed")))

        status = a.recovery_status
        findings = [f"Injected failure type: {a.failure_type}."]
        if status == "recovered":
            findings.append("The flow lost its route during chaos and was recovered over an alternative route.")
            findings.append("Post-recovery traffic ran over exactly the recovered route.")
        elif status == "not_required":
            findings.append("The flow's route survived the chaos; no recovery was needed.")
        elif status == "unrecoverable":
            findings.append("No alternative route existed; the failure was unrecoverable.")
        elif status == "not_attempted":
            findings.append("The flow was down during chaos but no recovery was attempted.")
        findings += [f"Missing data: {x}." for x in a.missing]

        return ResearchReport(
            experiment_id=experiment_id,
            overview=f"Experiment {experiment_id} ({exp.get('name', '')}): {a.failure_type}, recovery status {status}.",
            baseline=m["phases"]["baseline"] or {},
            failure={"type": a.failure_type, "chaos_phase": m["phases"]["chaos"] or {}},
            impact={"score": a.impact_score, "connectivity_during_chaos": m["connectivity_during_chaos"],
                    "latency_degradation_percent": a.latency_degradation,
                    "packet_loss_increase_points": a.packet_loss_degradation,
                    "throughput_degradation_percent": a.throughput_degradation},
            recovery={"status": status, "recoverable": a.recoverable, "time_seconds": a.recovery_time,
                      "effectiveness_percent": a.recovery_effectiveness},
            performance={"post_recovery": m["phases"]["post_recovery"] or {},
                         "post_recovery_latency_degradation_percent": a.post_recovery_latency_degradation},
            resilience_score=score,
            interpretation=interpret_resilience(score) if score is not None else "Insufficient data",
            disclaimer=DISCLAIMER, data_complete=a.data_complete, missing=a.missing,
            route_analysis=route, research_findings=findings)

    def export_experiment_configuration(self, experiment_id: str) -> ExperimentConfigurationExport:
        exp, _, rec = self._load(experiment_id)
        nid = exp["network_id"]
        strip = {"_id": 0, "network_id": 0}
        nodes = list(self.db.nodes.find({"network_id": nid}, strip))
        links = list(self.db.links.find({"network_id": nid}, strip))
        sims = [s for s in (rec["baseline"], rec["chaos_sim"], rec["post"]) if s]
        traffic = [{"simulation_id": s["id"], "phase": s.get("phase"), "source": s.get("source_node_id"),
                    "destination": s.get("destination_node_id"), "packet_count": s.get("packet_count"),
                    "packet_size": s.get("packet_size"), "random_seed": s.get("random_seed")} for s in sims]
        chaos = []
        for c in rec["chaos"]:
            events = list(self.db.chaos_events.find({"network_id": nid, "experiment_id": c["id"]}))
            chaos.append({"id": c["id"], "scenario_type": c.get("scenario_type"),
                          "events": [{"target_type": e["target_type"], "target_id": e["target_id"],
                                      "scenario_type": e["scenario_type"], "parameters": e.get("parameters", {})}
                                     for e in events]})
        return ExperimentConfigurationExport(
            experiment_id=experiment_id, network_id=nid,
            network_topology={"nodes": nodes, "links": links,
                              "note": "current topology; chaos reverts restore it after each run"},
            traffic_configuration=traffic,
            chaos_configuration={"scenario_type": chaos[0]["scenario_type"] if chaos else "unknown",
                                 "experiments": chaos},
            random_seed=next((s.get("random_seed") for s in sims if s.get("random_seed") is not None), None))
