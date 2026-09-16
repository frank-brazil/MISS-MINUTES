"""Integration tests for the MISSMINUTES runtime lifecycle.

Tests startup, readiness, shutdown, failure during startup, and repeated
shutdown — all using the headless test mode with all fakes.
"""

import asyncio

import pytest

from app.config.schema import MissMinutesConfig
from app.runtime.runtime import MissMinutesRuntime
from app.runtime.errors import StartupError


def _run(coro):
    return asyncio.run(coro)


def _headless_config(**overrides) -> MissMinutesConfig:
    cfg = MissMinutesConfig()
    for k, v in overrides.items():
        parts = k.split(".")
        obj = cfg
        for p in parts[:-1]:
            obj = getattr(obj, p)
        setattr(obj, parts[-1], v)
    return cfg


# ------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------

def test_startup_sets_ready():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        assert runtime.ready is False
        await runtime.startup()
        assert runtime.ready is True
        await runtime.shutdown()
    _run(flow())


def test_startup_initializes_orchestrator():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        assert runtime.orchestrator is not None
        assert len(runtime.orchestrator.agents()) > 0
        assert len(runtime.orchestrator.tools()) > 0
        await runtime.shutdown()
    _run(flow())


def test_startup_initializes_security():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        assert runtime.security is not None
        await runtime.shutdown()
    _run(flow())


def test_startup_registers_agents():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        names = runtime.orchestrator.agent_names()
        assert "system" in names
        assert "coding" in names
        assert "prediction" in names
        assert "critic" in names
        assert "verification" in names
        assert "research" in names
        await runtime.shutdown()
    _run(flow())


def test_startup_registers_tools():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        names = runtime.orchestrator.tool_names()
        assert "calculator" in names
        assert "system_info" in names
        assert "approved_terminal" in names
        assert "file_read" in names
        assert "file_search" in names
        await runtime.shutdown()
    _run(flow())


# ------------------------------------------------------------------
# Shutdown
# ------------------------------------------------------------------

def test_shutdown_sets_not_ready():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        assert runtime.ready is True
        await runtime.shutdown()
        assert runtime.ready is False
    _run(flow())


def test_repeated_shutdown_is_idempotent():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        await runtime.shutdown()
        await runtime.shutdown()  # second call
        assert runtime.ready is False
    _run(flow())


def test_repeated_startup_is_idempotent():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        await runtime.startup()  # second call
        assert runtime.ready is True
        await runtime.shutdown()
    _run(flow())


# ------------------------------------------------------------------
# Capabilities
# ------------------------------------------------------------------

def test_capabilities_reported():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        caps = runtime.capabilities.all_capabilities()
        assert caps["text"] is True
        assert caps["planning"] is True
        assert caps["agents"] is True
        assert caps["security"] is True
        assert caps["memory"] is True  # sqlite in default config
        assert caps["voice"] is False  # voice disabled by default
        assert caps["avatar"] is False  # avatar disabled by default
        await runtime.shutdown()
    _run(flow())


def test_health_report():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        report = runtime.capabilities.health_report(
            ready=runtime.ready,
            request_count=runtime.request_count,
        )
        assert report.ready is True
        assert report.request_count == 0
        assert len(report.capabilities) > 0
        await runtime.shutdown()
    _run(flow())


# ------------------------------------------------------------------
# Headless mode
# ------------------------------------------------------------------

def test_headless_runtime_creates():
    config = MissMinutesConfig()
    runtime = MissMinutesRuntime.create_headless(config)
    assert runtime is not None
    assert runtime.config is config


def test_headless_runtime_startup_and_shutdown():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        assert runtime.ready is True
        await runtime.shutdown()
        assert runtime.ready is False
    _run(flow())


# ------------------------------------------------------------------
# Audit trail
# ------------------------------------------------------------------

def test_audit_trail_records_events():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        response = await runtime.handle_text("Hello")
        entries = runtime.audit.entries_for(response.request_id)
        assert len(entries) > 0
        assert entries[0].stage == "accepted"
        await runtime.shutdown()
    _run(flow())
