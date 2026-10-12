"""Test fixtures.

By default tests run against an in-memory MongoDB (mongomock) so they need no server. To run the same
suite against a real MongoDB set NETCHAOS_TEST_DB=real; the database name must start with
"netchaos_test" because every collection is wiped before each test.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import database as dbmod
from app.config import get_mongodb_database

REAL = os.getenv("NETCHAOS_TEST_DB", "mock").lower() == "real"

if REAL:
    if not get_mongodb_database().startswith("netchaos_test"):
        raise RuntimeError("NETCHAOS_TEST_DB=real requires MONGODB_DATABASE to start with 'netchaos_test'")
else:
    import mongomock
    import pymongo
    # Some test modules build their own pymongo.MongoClient(...); route those to mongomock as well.
    pymongo.MongoClient = mongomock.MongoClient
    dbmod._client = mongomock.MongoClient()


@pytest.fixture(autouse=True)
def wipe_db():
    db = next(dbmod.get_mongo_db())
    for collection in db.list_collection_names():
        db[collection].delete_many({})
    from app.graph import graph_manager
    graph_manager.clear()


@pytest.fixture()
def client():
    yield TestClient(app)


@pytest.fixture()
def network_id(client) -> str:
    return client.post("/api/networks", json={"name": "Campus Network"}).json()["network_id"]


def make_node(client, network_id: str, name: str, node_type: str = "router") -> str:
    response = client.post(f"/api/networks/{network_id}/nodes", json={"name": name, "type": node_type})
    return response.json()["node_id"]


def link_payload(source: str, destination: str, **overrides) -> dict:
    return {"source": source, "destination": destination, "bandwidth": 100, "latency": 10, **overrides}


def build_canonical(client) -> dict:
    """Canonical topology: Router A -> B/C -> Router D (A-B-D is 20 ms, A-C-D is 40 ms). Returns ids by name."""
    nid = client.post("/api/networks", json={"name": "Canonical"}).json()["network_id"]
    nodes = {name: make_node(client, nid, name) for name in ("A", "B", "C", "D")}
    links = {}
    for a, b, lat in (("A", "B", 10), ("B", "D", 10), ("A", "C", 20), ("C", "D", 20)):
        r = client.post(f"/api/networks/{nid}/links", json=link_payload(nodes[a], nodes[b], latency=lat))
        links[a + b] = r.json()["link_id"]
    return {"network_id": nid, "nodes": nodes, "links": links}


def run_sim(client, nid: str, src: str, dst: str, **extra) -> dict:
    body = {"source": src, "destination": dst, "packet_count": 100, "packet_size": 1024, **extra}
    created = client.post(f"/api/networks/{nid}/traffic/simulations", json=body)
    assert created.status_code < 300, created.json()
    sid = created.json()["simulation_id"]
    ran = client.post(f"/api/networks/{nid}/traffic/simulations/{sid}/run")
    assert ran.status_code < 300, ran.json()
    return {"id": sid, **ran.json()}
