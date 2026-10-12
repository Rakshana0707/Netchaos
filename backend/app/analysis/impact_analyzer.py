"""Per-chaos-experiment impact, derived from real phase metrics and the recorded chaos events."""
from typing import List, Mapping

from app.schemas.history import FailureImpact


class ImpactAnalyzer:
    def analyze(self, chaos_docs: List[Mapping], events: List[Mapping], metrics: dict, partitions: int = 0) -> List[FailureImpact]:
        c, b = metrics["phases"]["chaos"], metrics["phases"]["baseline"]
        if c is None or b is None:
            return []
        down = not c["available"]
        degraded = down or any(
            (metrics[k] or 0) > 0 for k in ("latency_degradation_percent", "packet_loss_increase_points",
                                            "throughput_degradation_percent"))
        impacts = []
        for doc in chaos_docs:
            mine = [e for e in events if e.get("experiment_id") == doc["id"]]
            impacts.append(FailureImpact(
                failure_id=doc["id"],
                failure_type=doc.get("scenario_type", "unknown"),
                affected_nodes=len({e["target_id"] for e in mine if e.get("target_type") == "node"}),
                affected_links=len({e["target_id"] for e in mine if e.get("target_type") == "link"}),
                affected_traffic=1 if degraded else 0,
                partitions_created=partitions,
                packet_loss_change=metrics["packet_loss_increase_points"],
                latency_change_percent=metrics["latency_degradation_percent"],
                throughput_change_percent=metrics["throughput_degradation_percent"],
                availability_change=100.0 - metrics["connectivity_during_chaos"],
                impact_score=metrics["impact_score"],
            ))
        return sorted(impacts, key=lambda i: i.impact_score or 0.0, reverse=True)
