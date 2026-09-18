"""Integration tests for MISSMINUTES UI-02: Avatar Assets + Local Demo Mode.

Verifies:
1. Avatar PNGs are served via /assets mount
2. character.json is served
3. No external API references in frontend JS
4. Chat still works with asset mount
5. UI renders required elements
6. Local demo mode works without API keys
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config.settings import load_config
from app.runtime.runtime import MissMinutesRuntime


def _headless_runtime() -> MissMinutesRuntime:
    config = load_config()
    return MissMinutesRuntime.create_headless(config)


def _make_client():
    runtime = _headless_runtime()
    app = create_app(runtime=runtime)
    return TestClient(app, raise_server_exceptions=False)


class TestAvatarAssetsServed:
    def test_avatar_pngs_served(self):
        """All expression PNGs are accessible via /assets."""
        with _make_client() as client:
            for name in ["avatar", "neutral", "happy", "sad", "angry", "surprise", "thinking&confuse"]:
                resp = client.get(f"/assets/character/{name}.png")
                assert resp.status_code == 200, f"Failed to serve {name}.png"
                assert resp.headers["content-type"] == "image/png"
                assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', f"{name}.png is not valid PNG"

    def test_character_json_served(self):
        with _make_client() as client:
            resp = client.get("/assets/character/character.json")
            assert resp.status_code == 200
            data = resp.json()
            assert "expression_overlays" in data
            assert "expressions" in data["expression_overlays"]

    def test_expressions_json_served(self):
        with _make_client() as client:
            resp = client.get("/assets/expressions/expressions.json")
            assert resp.status_code == 200


class TestNoExternalAPIStrings:
    def test_no_provider_references_in_frontend(self):
        """Frontend JS files must not reference external API providers."""
        js_dir = Path("app/api/static/js")
        forbidden = ["openai", "gemini", "groq", "elevenlabs", "brave", "openrouter", "api_key"]
        for js_file in js_dir.glob("*.js"):
            content = js_file.read_text().lower()
            for keyword in forbidden:
                assert keyword not in content, f"{js_file.name} contains '{keyword}'"


class TestHeadlessChatWithAssets:
    def test_chat_works_with_asset_mount(self):
        """Adding /assets mount does not break chat."""
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "Hello"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_health_still_works(self):
        with _make_client() as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


class TestUIRendersRequiredElements:
    def test_index_renders_avatar_container(self):
        with _make_client() as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert 'id="avatar-container"' in resp.text
            assert 'id="avatar-svg"' in resp.text
            assert 'id="avatar-expression-overlay"' in resp.text

    def test_index_renders_demo_badge(self):
        with _make_client() as client:
            resp = client.get("/")
            assert "LOCAL DEMO MODE" in resp.text

    def test_index_renders_input_area(self):
        with _make_client() as client:
            resp = client.get("/")
            assert 'id="chat-input"' in resp.text
            assert 'id="btn-send"' in resp.text
            assert 'id="btn-mic"' in resp.text

    def test_index_renders_assistant_status(self):
        with _make_client() as client:
            resp = client.get("/")
            assert 'id="assistant-status"' in resp.text
            assert 'id="status-dot-main"' in resp.text
            assert 'id="status-label-main"' in resp.text

    def test_index_renders_system_status(self):
        with _make_client() as client:
            resp = client.get("/")
            assert 'id="status-grid"' in resp.text
            assert "Core" in resp.text
            assert "Memory" in resp.text
            assert "Voice" in resp.text
            assert "AI Provider" in resp.text

    def test_index_renders_quick_controls(self):
        with _make_client() as client:
            resp = client.get("/")
            assert "quick-controls" in resp.text
            assert "Memory" in resp.text
            assert "Tools" in resp.text
            assert "Voice" in resp.text
            assert "Settings" in resp.text

    def test_index_renders_avatar_assets_script(self):
        with _make_client() as client:
            resp = client.get("/")
            assert "avatar-assets.js" in resp.text


class TestAvatarAssetsJS:
    def test_avatar_assets_js_loads(self):
        with _make_client() as client:
            resp = client.get("/static/js/avatar-assets.js")
            assert resp.status_code == 200
            assert "MissMinutesAvatarAssets" in resp.text
            assert "EXPRESSION_PATHS" in resp.text
            assert "thinking%26confuse" in resp.text

    def test_avatar_js_loads(self):
        with _make_client() as client:
            resp = client.get("/static/js/avatar.js")
            assert resp.status_code == 200
            assert "MissMinutesAvatar" in resp.text
            assert "MissMinutesAvatarAssets" in resp.text


class TestLocalDemoMode:
    def test_no_api_keys_required(self):
        """System works without any API keys configured."""
        with _make_client() as client:
            resp = client.post("/api/chat", json={"message": "test"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"

    def test_avatar_state_works_without_avatar_enabled(self):
        with _make_client() as client:
            resp = client.get("/api/avatar/state")
            assert resp.status_code == 200
            data = resp.json()
            assert data["state"] == "idle"
            assert data["expression"] == "neutral"
            assert data["running"] is False

    def test_runtime_status_works(self):
        with _make_client() as client:
            resp = client.get("/runtime/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "ready" in data
            assert "capabilities" in data
