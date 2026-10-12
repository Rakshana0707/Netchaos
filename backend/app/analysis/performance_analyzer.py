"""Per-metric comparison across the lifecycle phases (baseline -> chaos -> post-recovery)."""
from typing import List, Optional

from app.schemas.history import MetricComparison, PerformanceAnalysis


class PerformanceAnalyzer:
    @staticmethod
    def _calc(baseline, worst, recovered, final, lower_is_better: bool) -> MetricComparison:
        """Compare phase values. Anything that is undefined (None) stays None instead of becoming 0."""
        cmp = MetricComparison(baseline=baseline, worst=worst, recovered=recovered, final=final)
        if baseline is None or worst is None:
            return cmp
        cmp.degradation_absolute = worst - baseline
        cmp.degradation_percentage = (cmp.degradation_absolute / baseline * 100) if baseline > 0 else None
        if recovered is None:
            return cmp
        cmp.recovery_improvement_absolute = worst - recovered
        cmp.recovery_improvement_percentage = ((worst - recovered) / worst * 100) if worst > 0 else None
        if worst == baseline:
            eff = 100.0 if recovered == baseline else 0.0
        elif lower_is_better:
            eff = (worst - recovered) / (worst - baseline) * 100
        else:
            eff = (recovered - worst) / (baseline - worst) * 100
        cmp.recovery_effectiveness = round(max(0.0, min(100.0, eff)), 2)
        return cmp

    def analyze_phases(self, m: dict) -> Optional[PerformanceAnalysis]:
        """Build the analysis from ``compute_phase_metrics`` output. None if there is no baseline/chaos data."""
        b, c, p = m["phases"]["baseline"], m["phases"]["chaos"], m["phases"]["post_recovery"]
        if b is None or c is None:
            return None
        final = p if p is not None else c

        def pick(view, key):
            return None if view is None else view[key]

        return PerformanceAnalysis(
            latency=self._calc(b["latency_ms"], c["latency_ms"], pick(p, "latency_ms"), pick(final, "latency_ms"), True),
            packet_loss=self._calc(b["packet_loss_percent"], c["packet_loss_percent"],
                                   pick(p, "packet_loss_percent"), final["packet_loss_percent"], True),
            throughput=self._calc(b["throughput_mbps"], c["throughput_mbps"],
                                  pick(p, "throughput_mbps"), final["throughput_mbps"], False),
            availability=self._calc(100.0, m["connectivity_during_chaos"], m["connectivity_preservation"],
                                    m["connectivity_preservation"], False),
        )

    def analyze_snapshots(self, snapshots: List[dict]) -> Optional[PerformanceAnalysis]:
        """APPROXIMATE fallback for experiments with no linked phases (e.g. created by hand).

        Baseline = first snapshot, worst = max/min over the window, recovered = second to last, final = last.
        Phases are inferred from ordering only; prefer linked phases (``analyze_phases``) for real analysis.
        """
        if not snapshots:
            return None

        def series(group: str, key: str) -> list:
            return [s.get(group, {}).get(key, 0) for s in snapshots]

        def build(values: list, worst: float, lower_is_better: bool) -> MetricComparison:
            recovered = values[-2] if len(values) > 1 else values[-1]
            return self._calc(values[0], worst, recovered, values[-1], lower_is_better)

        lats = series("traffic", "average_latency")
        pls = series("traffic", "packet_loss_percentage")
        thrs = series("traffic", "throughput")
        avls = series("connectivity", "traffic_availability")
        return PerformanceAnalysis(
            latency=build(lats, max(lats), True), packet_loss=build(pls, max(pls), True),
            throughput=build(thrs, min(thrs), False), availability=build(avls, min(avls), False),
        )
