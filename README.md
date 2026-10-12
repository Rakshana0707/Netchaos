# NetChaos – Network Resilience and Failure Recovery Simulator

FastAPI + MongoDB + NetworkX backend, React/Vite dashboard. NetChaos builds a network topology, simulates
traffic over it, injects reversible failures, detects them, recovers by rerouting, re-runs traffic over the
recovered route and computes resilience analytics. **Everything is a simulation** – metrics are simulated values,
not measurements of a real network, and the scores are internal indicators (see [ANALYTICS.md](ANALYTICS.md)).

## Lifecycle

```
TOPOLOGY -> TRAFFIC (baseline) -> CHAOS -> DETECTION -> IMPACT -> RECOVERY -> POST-RECOVERY TRAFFIC -> ANALYTICS -> RESILIENCE RESULT
```

Canonical example: Router A → B/C → Router D (A–B–D = 20 ms, A–C–D = 40 ms). Failing link B–D makes the flow
drop 100 %; recovery finds A→C→D; post-recovery traffic runs on exactly that route (40 ms, +100 % latency);
chaos is reverted afterwards. Failing Router D leaves no alternative route and is reported `unrecoverable`.

An experiment ties these records together through `POST /api/experiments/{id}/phases`; the batch runner
(`/api/experiment-plans`) does the whole sequence automatically and always reverts its chaos, even on errors.

## Run it

```bash
cp .env.example .env            # optional; defaults use the bundled MongoDB container
docker compose up --build       # dashboard http://localhost:3000, API docs http://localhost:8000/docs
```

Without Docker: a MongoDB on `localhost:27017` (or set `MONGODB_URI`), then

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000   # keep ONE worker
cd frontend && npm install && npm run dev                                            # http://localhost:5173
```

Health: `GET /health` (liveness), `GET /health/ready` (503 until MongoDB answers).
**Credentials:** never commit a `.env` or Atlas connection string; `.gitignore` excludes them. Pass `MONGODB_URI` through the environment.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest          # mongomock, no server needed
NETCHAOS_TEST_DB=real MONGODB_DATABASE=netchaos_test pytest            # against a real MongoDB
```

## Key endpoints (full per-module reference: [docs/MODULES.md](docs/MODULES.md))

| Purpose | Endpoint |
|---|---|
| Topology / traffic / chaos | `/api/networks/{id}/nodes|links|traffic/simulations|chaos/...` |
| Post-recovery traffic | `POST .../traffic/simulations` with `recovery_id` |
| Detection / recovery | `/api/networks/{id}/failures/detect`, `/api/networks/{id}/recovery` |
| Experiments | `/api/networks/{id}/experiments`, `/api/experiments/{id}` (+ `/phases`, `/complete`) |
| Analytics | `/api/networks/{id}/analytics/summary|failures`, `/api/experiments/{id}/report` |
| Batch runner / datasets | `/api/experiment-plans`, `/api/datasets` |

## Design notes and limitations
- The NetworkX graph lives in process memory: run a **single** uvicorn worker.
- One traffic flow per experiment; link failures, router failures and degradations are supported, as are multi-failure scenarios.
- Recovery time is simulator wall-clock, not protocol convergence time.
- A flow that is down has undefined latency (`null`), loss 100 %, throughput 0.
- Experiments created by hand without linked phases get only approximate snapshot-based analysis and are excluded from network summaries.
- The dataset module builds ML-style records from real linked experiments; legacy hand-inserted experiment documents are still accepted.
- No authentication, no WebSockets.

## Verification status
See the final report delivered with this repository: backend tests (mongomock) and the frontend build were run;
Docker image builds and a real-MongoDB run were **not verified** in the authoring sandbox (registry access blocked, no MongoDB server).
