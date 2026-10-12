from unittest.mock import patch


def test_liveness(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_ok_with_database(client):
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "up"


def test_readiness_503_when_database_down(client):
    with patch("app.main.ping_db", return_value=False):
        r = client.get("/health/ready")
    assert r.status_code == 503 and r.json()["database"] == "down"
