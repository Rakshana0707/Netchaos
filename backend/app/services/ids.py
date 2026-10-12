"""Sequential, per-network identifiers such as ``chaos_007`` or ``sim_012``.

Ids are zero-padded for readability, but the next number is found by comparing the *numeric* suffix:
sorting the ids as strings would put ``sim_1000`` before ``sim_999`` and hand out a duplicate.
"""
from pymongo.collection import Collection


def max_suffix(collection: Collection, query: dict, prefix: str) -> int:
    """Highest numeric suffix among ids ``<prefix><number>`` matching ``query`` (0 if there are none)."""
    highest = 0
    for doc in collection.find(query, {"id": 1, "_id": 0}):
        raw = str(doc.get("id", ""))
        if raw.startswith(prefix) and raw[len(prefix):].isdigit():
            highest = max(highest, int(raw[len(prefix):]))
    return highest


def next_id(collection: Collection, query: dict, prefix: str, width: int = 3) -> str:
    """The next unused id, e.g. ``next_id(db.traffic_simulations, {"network_id": n}, "sim_")`` -> ``sim_004``."""
    return f"{prefix}{max_suffix(collection, query, prefix) + 1:0{width}d}"
