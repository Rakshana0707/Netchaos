from typing import List

from app.schemas.history import RecoveryAnalysis, RouteSummary


def _diff(a, b):
    return None if a is None or b is None else a - b


class RecoveryAnalyzer:
    def analyze(self, recoveries: List[dict]) -> RecoveryAnalysis:
        recovered = [r for r in recoveries if r.get("recovery_status") == "RECOVERED"]
        routes = []
        for r in recoveries:
            orig, rec = r.get("original_route") or [], r.get("recovered_route") or []
            routes.append(RouteSummary(
                original_route=orig, recovered_route=rec,
                route_changed=bool(r.get("route_changed", False)),
                hop_difference=(len(rec) - len(orig)) if rec else None,
                latency_difference=_diff(r.get("recovered_latency"), r.get("original_latency")),
                bandwidth_difference=_diff(r.get("recovered_bandwidth"), r.get("original_bandwidth")),
            ))
        return RecoveryAnalysis(total_events=len(recoveries), successful=len(recovered),
                                failed=len(recoveries) - len(recovered), routes=routes)
