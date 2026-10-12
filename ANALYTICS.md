# NetChaos Analytics – definitions, formulas and limits

All numbers are computed from **simulated** traffic. They are internal project indicators for comparing
scenarios on one topology with each other; they are **not** real network measurements and **not** industry benchmarks.

## Where the data comes from
An experiment (`/api/experiments/{id}`) holds explicit links to the records of one traffic flow's lifecycle
(`POST /api/experiments/{id}/phases`, or filled automatically by the batch runner):

| Phase | Record |
|---|---|
| Baseline | `baseline_simulation_id` – traffic before the failure |
| Chaos | `chaos_experiment_ids`, `chaos_simulation_id` – failure injected, same flow re-run (a failed route = flow DOWN: loss 100 %, throughput 0, latency undefined) |
| Detection | `detection_id` |
| Recovery | `recovery_id` – alternative route computed by the recovery engine (no simulation is modified) |
| Post-recovery | `post_recovery_simulation_id` – new traffic sent over **exactly** the recovered route |

Nothing is inferred from timestamps when links exist. An experiment without links falls back to an
approximate snapshot comparison (`analyze_snapshots`) and is excluded from network aggregates.
Missing data is `null` with an explanation in `missing`; it is never replaced by 0.

## Metrics (`analysis/phase_metrics.py`)
- **Recovery status**: `recovered`, `not_required` (route survived), `unrecoverable` (no alternative route), `not_attempted`, `unknown`.
- **Recovery time** (s): detection `detected_at` → recovery record persisted. Simulator wall-clock, only defined when the flow was recovered and a detection exists.
- **Connectivity preservation** (%): 100 if the flow survived or was recovered, 0 otherwise.
- **Latency degradation** (%) = (chaos − baseline) / baseline × 100; `null` while the flow was down.
- **Packet-loss increase** (percentage points) = chaos loss − baseline loss.
- **Throughput degradation** (%) = (baseline − chaos) / baseline × 100.
- **Recovery effectiveness** (%): share of lost throughput regained after recovery (0 if unrecoverable).
- **Impact score** ∈ [0, 1], 0 = no impact: 0.30 connectivity + 0.20 latency (capped at +1000 %) + 0.20 packet loss + 0.15 throughput + 0.15 recovery time (capped at 10 s). A down flow scores the maximum on the first four terms.
- **Resilience score** (0–100) = 0.5 × average connectivity preservation + 0.5 × % of experiments recoverable. (The first draft used 0.4 + 0.4, which capped the score at 80; the weights were normalised so a fully resilient network scores 100.) Bands: ≥ 90 highly, ≥ 75 resilient, ≥ 50 moderately, otherwise low.

The weights and caps are design choices of this project, not derived from a standard.

## Limitations
- One flow per experiment; multi-flow experiments are not modelled.
- Metrics depend on the simulator's deterministic model (seeded packet loss, additive link latency).
- Recovery time is wall-clock of the simulator process, not a protocol convergence time.
- Averages over few experiments are dominated by single cases; treat results from fewer than ~10 experiments as illustrative.
