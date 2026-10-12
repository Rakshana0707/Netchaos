# NetChaos — Module 11: Automated Experiment Runner & Batch Chaos Testing

## Overview

The **Experiment Lab** (Module 11) provides an automated orchestration layer that runs fully controlled, repeatable NetChaos simulations without requiring manual intervention at each step. It wraps Modules 1–10 into a single automated workflow.

---

## Experiment Plans

An **Experiment Plan** is the top-level unit. It defines everything needed to repeat a simulation scenario identically.

### Schema

```json
{
  "name": "Packet Loss Sensitivity Study",
  "description": "Measure impact across 4 loss levels",
  "network_id": "net_001",
  "traffic": {
    "source": "node_001",
    "destination": "node_004",
    "packet_count": 1000,
    "packet_size": 1024
  },
  "chaos": {
    "type": "packet_loss",
    "target": "link_002",
    "parameters": {
      "loss_percentage": 10
    }
  },
  "recovery": {
    "enabled": true,
    "strategy": "shortest_hop"
  },
  "repetitions": 3,
  "random_seed": 42,
  "sweep": {
    "parameter": "loss_percentage",
    "values": [1, 5, 10, 20]
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable plan name |
| `description` | string (optional) | Purpose of the experiment |
| `network_id` | string | ID of the target network |
| `traffic` | object | Source, destination, packet parameters |
| `chaos` | object | Failure type, target element, parameters |
| `recovery` | object | Whether to invoke Dynamic Recovery (Module 5) |
| `repetitions` | int | How many times to repeat each scenario (max 100 total runs) |
| `random_seed` | int (optional) | Seed for reproducible simulations |
| `sweep` | object (optional) | Parameter sweep configuration |

---

## Experiment Runs

Each plan generates one or more **Runs**. For a plan with `repetitions=3` and a sweep of `[1, 5, 10, 20]`, the system creates **12 runs** (4 values × 3 repetitions).

### Run Fields

| Field | Description |
|-------|-------------|
| `run_id` | Unique run identifier |
| `experiment_id` | Linked history experiment (Module 7) |
| `run_number` | Sequence number within the plan |
| `status` | See Run States below |
| `started_at` | UTC timestamp |
| `completed_at` | UTC timestamp |
| `error` | Error message if failed |
| `configuration` | Snapshot of the sweep/repetition parameters |

---

## Lifecycle

### Plan States

```
CREATED → RUNNING → COMPLETED
                 ↘  PARTIAL   (some runs failed)
                 ↘  FAILED    (all runs failed)
                 ↘  CANCELLED (user cancelled)
```

### Per-Run Workflow

Each run executes the following steps in order. A failure at any step triggers immediate cleanup and marks the run FAILED:

1. Capture baseline state
2. Create History experiment record
3. Run baseline traffic simulation
4. Inject chaos (link failure, router failure, packet loss, latency, bandwidth reduction)
5. Run degraded traffic simulation
6. Trigger failure detection
7. Attempt recovery (if enabled)
8. Take monitoring snapshot
9. **Revert chaos (always, even on failure)**
10. Mark experiment complete in History
11. Mark run COMPLETED

### Status Distinction

> **Critical:** COMPLETED means the simulation executed correctly — even if the network could not be recovered.

```
Execution Status: COMPLETED
Network Outcome:  UNRECOVERABLE   ← correct and expected behavior
```

vs.

```
Execution Status: FAILED
Cause:            Service error, invalid configuration, etc.
```

---

## Parameter Sweeps

Sweeps automate varying a single parameter across multiple values.

### Supported Sweep Parameters

| Parameter | Scope | Example Values |
|-----------|-------|----------------|
| `loss_percentage` | Chaos: packet loss | `[0, 5, 10, 20]` |
| `additional_latency_ms` | Chaos: latency | `[20, 50, 100, 200]` |
| `reduction_percentage` | Chaos: bandwidth | `[10, 25, 50, 75]` |
| `packet_count` | Traffic | `[100, 500, 1000, 5000]` |
| `packet_size` | Traffic | `[64, 512, 1024, 9000]` |

### Example: Packet Loss Study (12 runs)

```json
{
  "repetitions": 3,
  "sweep": {
    "parameter": "loss_percentage",
    "values": [1, 5, 10, 20]
  }
}
```

Total = 4 values × 3 repetitions = **12 runs**

---

## Safety Limits

| Limit | Default |
|-------|---------|
| Maximum total runs per plan | **100** |
| Maximum repetitions without sweep | 100 |

Plans exceeding 100 total runs are **rejected before execution** with a 400 error.

---

## Chaos Scenario Library

The runner supports these chaos types:

| Type | Required Target | Parameters |
|------|----------------|------------|
| `link_failure` | `link_id` | None |
| `router_failure` | `node_id` | None |
| `packet_loss` | `link_id` | `loss_percentage` (0–100) |
| `latency` | `link_id` | `additional_latency_ms` (≥0) |
| `bandwidth_reduction` | `link_id` | `bandwidth` (Mbps > 0) |

---

## Cleanup Guarantee

The runner wraps every run execution in a `try/finally` pattern:

```python
try:
    execute_run()
finally:
    revert_all_active_chaos(network_id)
```

If cleanup fails, the run is still marked FAILED but a warning is recorded. The network state is never left permanently corrupted.

---

## Cancellation

```
POST /api/experiment-plans/{plan_id}/cancel
```

- The flag is checked **between** runs (not mid-run)
- The current run completes and chaos is reverted cleanly
- Subsequent queued runs are skipped and marked CANCELLED
- Plan status becomes CANCELLED

---

## Reproducibility

Each run stores its full configuration snapshot:

```json
{
  "configuration": {
    "sweep_parameter": "loss_percentage",
    "sweep_value": 10,
    "repetition": 2
  }
}
```

If a `random_seed` is provided in the plan, it is passed to the traffic simulation ensuring deterministic packet-loss rolls.

> **Note:** Reproducibility applies to deterministic simulation components. External network state changes between runs may affect outcomes.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/experiment-plans` | Create a new plan |
| `GET` | `/api/experiment-plans/{plan_id}` | Get plan status & runs |
| `POST` | `/api/experiment-plans/{plan_id}/run` | Start execution (async background thread) |
| `POST` | `/api/experiment-plans/{plan_id}/cancel` | Request cancellation |
| `GET` | `/api/experiment-plans/{plan_id}/results` | Get results with analytics |
| `GET` | `/api/experiment-plans/{plan_id}/export/csv` | Download results as CSV |
| `GET` | `/api/experiment-plans/{plan_id}/export/json` | Download results as JSON |

---

## Batch Analytics

After completion, `/results` returns Module 10 analytics for each completed run:

```json
{
  "plan_id": "plan_001_001",
  "total_runs": 12,
  "completed_runs": 12,
  "results": [
    {
      "run_id": "plan_001_001_run001",
      "experiment_id": "exp_001",
      "scenario": { "sweep_parameter": "loss_percentage", "sweep_value": 1, "repetition": 1 },
      "analytics": {
        "resilience_score": 0.87,
        "impact_score": 0.13,
        "recovery_time_seconds": 0.5,
        "connectivity_preservation": 0.92,
        "recovery_effectiveness": 0.95
      }
    }
  ]
}
```

---

## Export Formats

### CSV

Includes one row per completed run:

```
plan_id,run_id,experiment_id,sweep_parameter,sweep_value,repetition,status,
resilience_score,impact_score,recovery_time_seconds,connectivity_preservation,recovery_effectiveness
```

### JSON

Full structured export including all analytics fields, suitable for import into external analysis tools.

---

## Research Use Cases

### 1. Failure Sensitivity Analysis

> *How does resilience change as packet loss increases?*

Set up a sweep over `loss_percentage: [0, 5, 10, 20, 50]` with `repetitions: 3`. Compare resilience scores across values **within the tested simulations**.

### 2. Recovery Evaluation

> *How does recovery time vary across failure types?*

Create separate plans for each chaos type (`link_failure`, `router_failure`, `packet_loss`). Compare `recovery_time_seconds` averages across plans.

### 3. Topology Comparison

> *Which topology preserved more connectivity?*

Apply the same plan to networks with different topologies (ring vs mesh vs star). Compare `connectivity_preservation` scores.

### 4. Failure Ranking

> *Which failures caused the largest observed impact?*

Run a failure-type matrix: one plan per failure type, same traffic and topology. Sort by `impact_score` to identify highest-risk failure modes **within the tested scenarios**.

### 5. Routing Evaluation

> *Which routing strategy performed better under tested conditions?*

Run the same experiment plan twice with `recovery.strategy` set to different values. Compare recovery metrics.

> ⚠️ All conclusions apply **within the tested simulations only**. No universal claims should be drawn.

---

## Complete Example: Packet Loss Study

```bash
# 1. Create plan
POST /api/experiment-plans
{
  "name": "Packet Loss Study",
  "network_id": "net_001",
  "traffic": { "source": "node_001", "destination": "node_004", "packet_count": 500, "packet_size": 1024 },
  "chaos": { "type": "packet_loss", "target": "link_003" },
  "recovery": { "enabled": true },
  "repetitions": 3,
  "sweep": { "parameter": "loss_percentage", "values": [1, 5, 10, 20] }
}
→ Returns plan_id

# 2. Start execution (12 runs will run sequentially)
POST /api/experiment-plans/{plan_id}/run

# 3. Poll progress
GET /api/experiment-plans/{plan_id}
→ { status: "RUNNING", completed_runs: 4, total_runs: 12, progress_percentage: 33 }

# 4. Get results when COMPLETED
GET /api/experiment-plans/{plan_id}/results

# 5. Export
GET /api/experiment-plans/{plan_id}/export/csv
```

---

## Frontend: Experiment Lab

Navigate to the **Experiment Lab** tab in the NetChaos dashboard.

- **Builder Tab**: Configure all experiment parameters, enable parameter sweep, and launch
- **Active Run Tab**: Live progress bar, per-run status log, and cancel button
- **Results Section**: Resilience table per run, ⬇ CSV / ⬇ JSON export buttons

---

## Known Limitations

1. Runs are executed sequentially (one at a time) — concurrent execution is not supported
2. Sweep only supports a single parameter per plan
3. The `random_seed` is applied only to traffic simulations; topology operations are deterministic
4. If the MongoDB connection drops mid-run, state may be inconsistent (shown as RUNNING)
5. Analytics are only populated when Module 10 `ResilienceAnalyticsService` has sufficient experiment data

## Future Extensions

- Multi-parameter sweeps (e.g. vary both latency and loss simultaneously)  
- Concurrent run execution with a worker pool
- Cross-network topology comparison in a single plan
- Scheduled/recurring experiment plans
- Webhook notifications on plan completion
- Direct integration with Module 10 batch analytics dashboard
