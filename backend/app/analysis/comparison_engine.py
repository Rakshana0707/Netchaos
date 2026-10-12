from typing import List


def _get(perf, metric: str, key: str):
    return perf[metric][key] if perf else None


class ComparisonEngine:
    def compare_experiments(self, expr_details: List[dict]) -> List[dict]:
        """Side-by-side figures per experiment. Values that are undefined for an experiment stay None."""
        results = []
        for e in expr_details:
            perf = e.get("performance_analysis")
            impacts = e.get("failure_impacts", [])
            metrics = e.get("metrics") or {}
            results.append({
                "experiment_id": e["experiment"]["id"],
                "experiment_name": e["experiment"]["name"],
                "failure_type": impacts[0]["failure_type"] if impacts else "Unknown",
                "packet_loss": _get(perf, "packet_loss", "worst"),
                "latency_degradation": _get(perf, "latency", "degradation_absolute"),
                "throughput": _get(perf, "throughput", "worst"),
                "availability": _get(perf, "availability", "worst"),
                "recovery_time": metrics.get("recovery_time_seconds"),
                "recovery_effectiveness": metrics.get("recovery_effectiveness_percent"),
                "affected_traffic": sum(i["affected_traffic"] for i in impacts),
            })
        return results
