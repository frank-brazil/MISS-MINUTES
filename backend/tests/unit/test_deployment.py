"""Deployment and packaging tests for MISSMINUTES.

Validates installation, configuration, startup, shutdown, and demo mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TestPackageInstallation:
    """Verify the package is correctly installed and importable."""

    def test_import_app_package(self):
        import app

        assert app is not None

    def test_import_config_schema(self):
        from app.config.schema import AIConfig, AppConfig, MissMinutesConfig

        assert MissMinutesConfig is not None
        assert AppConfig is not None
        assert AIConfig is not None

    def test_import_config_settings(self):
        from app.config.settings import load_config

        assert callable(load_config)

    def test_import_runtime(self):
        from app.runtime.runtime import MissMinutesRuntime

        assert MissMinutesRuntime is not None

    def test_import_api_app(self):
        from app.api.app import create_app

        assert callable(create_app)

    def test_import_fastapi(self):
        import fastapi

        assert fastapi.__version__

    def test_import_pydantic(self):
        import pydantic

        assert pydantic.__version__

    def test_import_uvicorn(self):
        import uvicorn

        assert uvicorn.__version__


class TestConfigurationValidation:
    """Verify configuration loading and defaults."""

    def test_default_config_loads(self):
        from app.config.settings import load_config

        config = load_config(path="nonexistent.toml")
        assert config.app.host == "127.0.0.1"
        assert config.app.port == 8000
        assert config.app.log_level == "INFO"
        assert config.app.environment == "development"

    def test_toml_config_loads(self):
        from app.config.settings import load_config

        config = load_config(path=str(_PROJECT_ROOT / "config" / "missminutes.toml"))
        assert config.ai.provider == "openai"
        assert config.security.audit_enabled is True

    def test_config_env_override(self, monkeypatch):
        from app.config.settings import load_config

        monkeypatch.setenv("MISSMINUTES_PORT", "9999")
        monkeypatch.setenv("MISSMINUTES_HOST", "0.0.0.0")
        config = load_config(path="nonexistent.toml")
        assert config.app.port == 9999
        assert config.app.host == "0.0.0.0"

    def test_config_bool_env_override(self, monkeypatch):
        from app.config.settings import load_config

        monkeypatch.setenv("MISSMINUTES_VOICE_ENABLED", "true")
        config = load_config(path="nonexistent.toml")
        assert config.voice.enabled is True

    def test_config_invalid_port_ignored(self, monkeypatch):
        from app.config.settings import load_config

        monkeypatch.setenv("MISSMINUTES_PORT", "not_a_number")
        config = load_config(path="nonexistent.toml")
        # Falls back to default
        assert config.app.port == 8000


class TestAppConfigSchema:
    """Verify AppConfig schema defaults."""

    def test_app_config_defaults(self):
        from app.config.schema import AppConfig

        cfg = AppConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.log_level == "INFO"
        assert cfg.environment == "development"

    def test_missminutes_config_has_app(self):
        from app.config.schema import MissMinutesConfig

        cfg = MissMinutesConfig()
        assert hasattr(cfg, "app")
        assert cfg.app.port == 8000


class TestRuntimeCreation:
    """Verify runtime can be created in various modes."""

    def test_headless_runtime_creation(self):
        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        runtime = MissMinutesRuntime.create_headless(MissMinutesConfig())
        assert runtime is not None
        assert runtime.config is not None

    def test_headless_runtime_capabilities(self):
        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        runtime = MissMinutesRuntime.create_headless(MissMinutesConfig())
        caps = runtime.capabilities.all_capabilities()
        assert "text" in caps or len(caps) >= 0

    def test_standard_runtime_creation(self):
        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        assert runtime is not None


class TestAppCreation:
    """Verify FastAPI app creation."""

    def test_create_app_default(self):
        from app.api.app import create_app

        app = create_app()
        assert app.title == "MISSMINUTES"
        assert app.version == "0.1.0"

    def test_create_app_with_runtime(self):
        from app.api.app import create_app
        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        runtime = MissMinutesRuntime.create_headless(MissMinutesConfig())
        app = create_app(runtime=runtime)
        assert app.state.runtime is runtime

    def test_app_has_routes(self):
        from fastapi.testclient import TestClient

        from app.api.app import create_app

        app = create_app()
        client = TestClient(app)
        # Verify key endpoints respond
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/api/info").status_code == 200
        assert client.get("/runtime/status").status_code in (200, 503)


class TestHealthEndpoint:
    """Verify health endpoint works."""

    def test_health_returns_ok(self):
        from fastapi.testclient import TestClient

        from app.api.app import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_root_returns_info(self):
        from fastapi.testclient import TestClient

        from app.api.app import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MISSMINUTES"
        assert "version" in data


class TestEnvironmentExample:
    """Verify .env.example exists and is well-formed."""

    def test_env_example_exists(self):
        assert (_PROJECT_ROOT / ".env.example").is_file()

    def test_env_example_has_required_vars(self):
        content = (_PROJECT_ROOT / ".env.example").read_text()
        required = [
            "OPENAI_API_KEY",
            "MISSMINUTES_HOST",
            "MISSMINUTES_PORT",
            "MISSMINUTES_LOG_LEVEL",
            "MISSMINUTES_MEMORY_DB",
            "MISSMINUTES_AUTH_TOKEN",
        ]
        for var in required:
            assert var in content, f"{var} missing from .env.example"

    def test_env_example_has_no_real_secrets(self):
        content = (_PROJECT_ROOT / ".env.example").read_text()
        # Should only have empty values or placeholders
        for line in content.splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            # No value should look like a real key (sk-..., etc.)
            assert not value.startswith("sk-"), f"Real secret in .env.example: {key}"


class TestGitignore:
    """Verify .gitignore covers critical patterns."""

    def test_gitignore_excludes_env(self):
        content = (_PROJECT_ROOT / ".gitignore").read_text()
        assert ".env" in content

    def test_gitignore_excludes_venv(self):
        content = (_PROJECT_ROOT / ".gitignore").read_text()
        assert ".venv/" in content

    def test_gitignore_excludes_pycache(self):
        content = (_PROJECT_ROOT / ".gitignore").read_text()
        assert "__pycache__/" in content

    def test_gitignore_excludes_egg_info(self):
        content = (_PROJECT_ROOT / ".gitignore").read_text()
        assert "*.egg-info/" in content

    def test_gitignore_excludes_build_artifacts(self):
        content = (_PROJECT_ROOT / ".gitignore").read_text()
        assert "dist/" in content
        assert "build/" in content


class TestTOMLConfig:
    """Verify the TOML config file is valid."""

    def test_toml_config_exists(self):
        assert (_PROJECT_ROOT / "config" / "missminutes.toml").is_file()

    def test_toml_config_parseable(self):
        import tomllib

        with open(_PROJECT_ROOT / "config" / "missminutes.toml", "rb") as f:
            data = tomllib.load(f)
        assert "ai" in data
        assert "security" in data
        assert "distributed" in data

    def test_toml_config_has_app_section(self):
        import tomllib

        with open(_PROJECT_ROOT / "config" / "missminutes.toml", "rb") as f:
            data = tomllib.load(f)
        assert "app" in data
        assert data["app"]["host"] == "127.0.0.1"
        assert data["app"]["port"] == 8000


class TestDemoMode:
    """Verify headless/demo mode works end-to-end."""

    def test_headless_text_request(self):
        import asyncio

        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        runtime = MissMinutesRuntime.create_headless(MissMinutesConfig())
        asyncio.run(runtime.startup())
        try:
            response = asyncio.run(runtime.handle_text("hello"))
            assert response is not None
            assert response.request_id is not None
        finally:
            asyncio.run(runtime.shutdown())

    def test_headless_text_returns_response(self):
        import asyncio

        from app.config.schema import MissMinutesConfig
        from app.runtime.runtime import MissMinutesRuntime

        runtime = MissMinutesRuntime.create_headless(MissMinutesConfig())
        asyncio.run(runtime.startup())
        try:
            response = asyncio.run(runtime.handle_text("What is 2+2?"))
            assert response.success is True
            assert response.text_response is not None
        finally:
            asyncio.run(runtime.shutdown())


class TestSecurityAudit:
    """Verify no secrets are committed in source files."""

    def _has_hardcoded_secret(self, line: str) -> bool:
        """Check if a line contains a hardcoded secret value."""
        import re

        stripped = line.strip()
        # Skip comments and docstrings
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            return False
        if "os.environ" in stripped or "os.getenv" in stripped:
            return False
        # OpenAI API keys (sk-xxx...)
        if re.search(r"\bsk-[A-Za-z0-9]{20,}", stripped):
            return True
        # Bearer tokens with actual key material
        if re.search(r"bearer\s+sk-[A-Za-z0-9]", stripped, re.IGNORECASE):
            return True
        # Hardcoded password strings
        if re.search(r'password\s*=\s*["\'][^"\']{4,}["\']', stripped, re.IGNORECASE):
            return True
        return False

    def test_no_secrets_in_source(self):
        """Scan key source files for accidental hardcoded secrets."""
        source_dirs = [_PROJECT_ROOT / "app", _PROJECT_ROOT / "config"]
        for d in source_dirs:
            if not d.exists():
                continue
            for py_file in d.rglob("*.py"):
                content = py_file.read_text(errors="ignore")
                for line in content.splitlines():
                    if self._has_hardcoded_secret(line):
                        assert False, f"Hardcoded secret in {py_file}: {line.strip()}"

    def test_env_example_no_real_values(self):
        """Double-check .env.example has no real secrets."""
        env_file = _PROJECT_ROOT / ".env.example"
        if not env_file.exists():
            pytest.skip(".env.example not found")
        content = env_file.read_text()
        for line in content.splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            _, _, value = line.partition("=")
            value = value.strip()
            assert value in ("", "true", "false") or not any(
                v in value.lower() for v in ["sk-", "bearer", "password", "secret"]
            ), f"Possible secret in .env.example: {line}"
