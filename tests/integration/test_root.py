from fastapi.testclient import TestClient

from app.api.app import app


client = TestClient(app)


def test_root_returns_200() -> None:
    response = client.get("/")
    assert response.status_code == 200


def test_root_returns_missminutes_identity() -> None:
    response = client.get("/")
    data = response.json()
    assert data["name"] == "MISSMINUTES"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"
    assert "description" in data
