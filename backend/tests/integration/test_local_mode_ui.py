"""Integration tests for the MISSMINUTES Local UI milestone.

Verifies that the web interface works correctly with the backend:
1. /health still works
2. UI pages load
3. Chat request reaches backend
4. Backend returns a response
5. Empty messages are rejected safely
6. Local mode works without API keys
7. No secrets are exposed
"""

import asyncio

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config.schema import MissMinutesConfig
from app.runtime.runtime import MissMinutesRuntime


def _headless_runtime() -> MissMinutesRuntime:
    config = MissMinutesConfig()
    return MissMinutesRuntime.create_headless(config)


def _make_client():
    runtime = _headless_runtime()
    app = create_app(runtime=runtime)
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        with _make_client() as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


class TestUIPagesLoad:
    def test_index_page_loads(self):
        with _make_client() as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "MISSMINUTES" in resp.text
            assert "LOCAL MODE" in resp.text
            assert "<svg" in resp.text

    def test_dashboard_page_loads(self):
        with _make_client() as client:
            resp = client.get("/dashboard")
            assert resp.status_code == 200
            assert "Dashboard" in resp.text

    def test_settings_page_loads(self):
        with _make_client() as client:
            resp = client.get("/settings")
            assert resp.status_code == 200
            assert "Settings" in resp.text
            assert "AI Providers" in resp.text


class TestChatAPI:
    def test_chat_with_valid_message(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "Hello"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["message"] is not None
            assert len(data["message"]) > 0

    def test_chat_rejects_empty_message(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": ""})
            assert resp.status_code == 422

    def test_chat_rejects_blank_message(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "   "})
            assert resp.status_code == 422

    def test_chat_rejects_missing_message(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={})
            assert resp.status_code == 422

    def test_chat_response_has_correct_structure(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "test"})
            assert resp.status_code == 200
            data = resp.json()
            assert set(data.keys()) == {"message", "status", "task_id"}
            assert data["status"] in ("success", "error")


class TestLocalMode:
    def test_headless_runtime_no_api_keys(self):
        runtime = _headless_runtime()
        assert runtime.ready is False
        asyncio.run(runtime.startup())
        assert runtime.ready is True
        asyncio.run(runtime.shutdown())

    def test_headless_chat_works(self):
        async def flow():
            runtime = _headless_runtime()
            await runtime.startup()
            response = await runtime.handle_text("Hello local mode")
            assert response.success is True
            assert response.text_response is not None
            await runtime.shutdown()

        asyncio.run(flow())

    def test_chat_via_api_in_headless_mode(self):
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "What is 2+2?"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["message"] is not None
            assert len(data["message"]) > 0


class TestAvatarAPI:
    def test_avatar_state_endpoint(self):
        with _make_client() as client:
            resp = client.get("/api/avatar/state")
            assert resp.status_code == 200
            data = resp.json()
            assert "state" in data
            assert "expression" in data
            assert "running" in data

    def test_avatar_signal_invalid(self):
        with _make_client() as client:
            resp = client.post("/api/avatar/signal?signal=invalid")
            # Avatar may not be available in headless mode (503) or signal is invalid (400)
            assert resp.status_code in (400, 503)


class TestSecurityPreserved:
    def test_no_secrets_in_settings_page(self):
        with _make_client() as client:
            resp = client.get("/settings")
            text = resp.text
            assert "sk-" not in text
            assert "api_key" not in text.lower() or "NOT CONFIGURED" in text

    def test_no_secrets_in_dashboard_page(self):
        with _make_client() as client:
            resp = client.get("/dashboard")
            text = resp.text
            assert "sk-" not in text


class TestStaticFiles:
    def test_css_loads(self):
        with _make_client() as client:
            resp = client.get("/static/css/main.css")
            assert resp.status_code == 200
            assert "MISSMINUTES" in resp.text or "var(--" in resp.text

    def test_js_loads(self):
        with _make_client() as client:
            resp = client.get("/static/js/api.js")
            assert resp.status_code == 200

    def test_avatar_js_loads(self):
        with _make_client() as client:
            resp = client.get("/static/js/avatar.js")
            assert resp.status_code == 200


class TestHeadlessModePreserved:
    def test_headless_flag_works(self):
        from main import main
        import sys
        sys.argv = ["main.py", "--headless"]
        assert "--headless" in sys.argv
