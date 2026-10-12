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


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_mongodb_uri())
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
