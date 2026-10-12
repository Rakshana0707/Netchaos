"""Application settings, read from environment variables."""
import os

def get_mongodb_uri() -> str:
    try:
        return os.environ["MONGODB_URI"]
    except KeyError:
        return "mongodb://localhost:27017/"

def get_mongodb_database() -> str:
    return os.getenv("MONGODB_DATABASE", "netchaos")

# --- Module 2: traffic simulation limits -------------------------------------
MAX_PACKET_COUNT = 100_000  # per simulation; keeps one request to well under a second of CPU
MAX_PACKET_SIZE = 65_535  # bytes, the largest possible IP packet

def get_max_stored_packets() -> int:
    """Largest simulation whose individual packets may be saved to the database."""
    return int(os.getenv("TRAFFIC_MAX_STORED_PACKETS", "1000"))
