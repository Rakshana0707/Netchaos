"""PyMongo database access."""
import logging
from collections.abc import Iterator

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.config import get_mongodb_uri, get_mongodb_database

log = logging.getLogger(__name__)

_client: MongoClient | None = None

# (collection, keys, unique). Ids are only unique per network, so most indexes include network_id.
INDEXES: list[tuple[str, list[tuple[str, int]], bool]] = [
    ("networks", [("id", 1)], True),
    ("nodes", [("network_id", 1), ("id", 1)], True),
    ("links", [("network_id", 1), ("id", 1)], True),
    ("traffic_simulations", [("network_id", 1), ("id", 1)], True),
    ("chaos_experiments", [("network_id", 1), ("id", 1)], True),
    ("chaos_events", [("network_id", 1), ("id", 1)], True),
    ("failure_detections", [("network_id", 1), ("id", 1)], True),
    ("recovery_events", [("network_id", 1), ("id", 1)], True),
    ("experiments", [("network_id", 1), ("id", 1)], True),
    ("monitoring_snapshots", [("network_id", 1), ("timestamp", 1)], False),
]


def seed_database(db: Database, drop_first: bool = False) -> None:
    """Pre-populate the database with initial networks/nodes/links from mongodb_seed."""
    import os
    from bson import json_util

    if not drop_first and db.networks.count_documents({}) > 0:
        return

    seed_dirs = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "mongodb_seed"),
        os.path.join(os.path.dirname(__file__), "..", "..", "mongodb_seed"),
        os.path.abspath("mongodb_seed"),
        os.path.abspath("../mongodb_seed"),
    ]
    target_dir = None
    for d in seed_dirs:
        if os.path.isdir(d):
            target_dir = d
            break

    if not target_dir:
        log.warning("Could not locate mongodb_seed directory for auto-seeding.")
        return

    collections = [
        "networks",
        "nodes",
        "links",
        "traffic_simulations",
        "chaos_experiments",
        "failure_detections",
        "recovery_events",
        "experiment_plans",
        "datasets",
        "dataset_records",
        "chaos_events",
        "experiments",
        "packets",
        "monitoring_snapshots",
    ]

    for col in collections:
        if drop_first:
            db[col].drop()
        fpath = os.path.join(target_dir, f"{col}.json")
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    data = json_util.loads(content)
                    if data:
                        if isinstance(data, list):
                            db[col].insert_many(data)
                        else:
                            db[col].insert_one(data)
            except Exception as e:
                log.warning("Failed to auto-seed %s: %s", col, e)
    log.info("Seeded database with clean seed files from %s (drop_first=%s)", target_dir, drop_first)


def reset_database() -> dict[str, str]:
    """Drops and reloads seed dataset across all collections, and clears in-memory graphs."""
    db = get_mongo_client()[get_mongodb_database()]
    seed_database(db, drop_first=True)
    try:
        from app.graph import graph_manager
        graph_manager.clear()
    except Exception as exc:
        log.warning("Could not clear graph manager: %s", exc)
    return {"status": "ok", "message": "Database and in-memory topology reset to original seed data"}


def _seed_mock_db(db: Database) -> None:
    seed_database(db, drop_first=False)


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        import os
        uri = get_mongodb_uri()
        force_mock = os.getenv("USE_MOCK_DB", "").lower() in ("true", "1", "yes") or uri == "mock"
        if not force_mock:
            try:
                real_client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                real_client.admin.command("ping")
                _client = real_client
                log.info("Successfully connected to MongoDB at %s", uri)
            except Exception as exc:
                log.warning("Could not connect to MongoDB at %s (%s). Falling back to in-memory mongomock database.", uri, exc)
                force_mock = True

        if force_mock:
            import mongomock
            _client = mongomock.MongoClient()
            _seed_mock_db(_client[get_mongodb_database()])
    return _client


def get_mongo_db() -> Iterator[Database]:
    client = get_mongo_client()
    yield client[get_mongodb_database()]


def ping_db() -> bool:
    """True if MongoDB answers; never raises (used by the readiness probe)."""
    try:
        get_mongo_client().admin.command("ping")
        return True
    except Exception:
        return False


def init_db() -> None:
    """Create MongoDB indexes. A duplicate in existing data is logged, not fatal."""
    db = get_mongo_client()[get_mongodb_database()]
    for collection, keys, unique in INDEXES:
        try:
            db[collection].create_index(keys, unique=unique)
        except DuplicateKeyError as exc:
            log.warning("Could not create unique index on %s: %s", collection, exc)
