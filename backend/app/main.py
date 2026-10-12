import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chaos import router as chaos_router
from app.api.topology import router as topology_router
from app.api.traffic import router as traffic_router
from app.api.failures import router as failures_router
from app.api.recovery import router as recovery_router
from app.api.monitoring import router as monitoring_router
from app.api.history import router as history_router
from app.api.analytics import router as analytics_router
from app.api.runner import router as runner_router
from app.api.dataset import router as dataset_router
from app.database.database import init_db, ping_db
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.errors import register_exception_handlers



@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception:  # MongoDB not reachable yet: stay up, /health/ready reports 503 until it is
        logging.getLogger(__name__).exception("Could not initialise MongoDB indexes at startup")
    yield


app = FastAPI(
    title="NetChaos API",
    description="Module 1: network topology (MongoDB + in-memory NetworkX graph). "
    "Module 2: deterministic traffic simulation on top of that topology. "
    "Module 3: reversible chaos injection (failures and degradations) applied to that same topology."
    "Module 4: failure detection based on current state. "
    "Module 5: dynamic recovery. "
    "Module 6: network monitoring & performance analysis."
    "Module 7: network history & analysis.",
    version="0.7.0",

    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(topology_router)
app.include_router(traffic_router)
app.include_router(chaos_router)
app.include_router(failures_router)
app.include_router(recovery_router)
app.include_router(monitoring_router)
app.include_router(history_router)
app.include_router(analytics_router)
app.include_router(runner_router)
app.include_router(dataset_router)

@app.get("/health", tags=["health"], summary="Liveness check")

def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], summary="Readiness check (includes MongoDB)")
def ready():
    if ping_db():
        try:
            init_db()  # idempotent; covers a database that came up after the API did
        except Exception:
            logging.getLogger(__name__).exception("Index creation failed")
        return {"status": "ok", "database": "up"}
    return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
