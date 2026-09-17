from app.api.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_root_returns_200() -> None:
    response = client.get("/api/info")
    assert response.status_code == 200


def test_root_returns_missminutes_identity() -> None:
    response = client.get("/api/info")
    data = response.json()
    assert data["name"] == "MISSMINUTES"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"
    assert "description" in data
