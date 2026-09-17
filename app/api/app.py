from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import router
from app.core.ai import AIModel
from app.core.orchestrator import Orchestrator
from app.distributed.httpapi import create_master_app
from app.memory.base import Memory
from app.runtime.runtime import MissMinutesRuntime
from app.security.manager import SecurityManager

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "api" / "static"
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "app" / "api" / "templates"


def create_app(
    *,
    orchestrator: Orchestrator | None = None,
    ai_model: AIModel | None = None,
    memory: Memory | None = None,
    distributed_coordinator=None,
    distributed_config=None,
    security_manager: SecurityManager | None = None,
    runtime: MissMinutesRuntime | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: initialize the runtime if provided
        if runtime is not None and not runtime.ready:
            logger.info("Lifespan: starting runtime")
            await runtime.startup()
        yield
        # Shutdown: clean up the runtime
        if runtime is not None:
            logger.info("Lifespan: shutting down runtime")
            await runtime.shutdown()

    app = FastAPI(
        title="MISSMINUTES",
        version="0.1.0",
        description="Personal intelligent AI computer agent",
        lifespan=lifespan,
    )

    if runtime is not None:
        # Runtime-backed mode: use the runtime's orchestrator
        app.state.runtime = runtime
        app.state.orchestrator = runtime.orchestrator
        if runtime.security is not None:
            app.state.security_manager = runtime.security
    else:
        # Legacy mode: orchestrator provided directly
        resolved = (
            orchestrator
            if orchestrator is not None
            else Orchestrator(
                ai_model=ai_model,
                memory=memory,
                security=security_manager,
            )
        )
        app.state.orchestrator = resolved
        if security_manager is not None:
            app.state.security_manager = security_manager

    app.include_router(router)

    # Mount static files for web UI
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Mount avatar assets (PNGs, character.json, etc.)
    _ASSETS_DIR = Path(__file__).resolve().parents[2] / "ui" / "avatar" / "assets"
    if _ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

    # UI routes
    @app.get("/", response_class=HTMLResponse)
    async def ui_root(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/ui", response_class=HTMLResponse)
    async def ui_redirect(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def ui_dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "dashboard.html")

    @app.get("/settings", response_class=HTMLResponse)
    async def ui_settings(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "settings.html")

    # Optional distributed master: when a coordinator is supplied, expose the
    # /distributed/* API on this app.
    if distributed_coordinator is not None:
        master = create_master_app(
            coordinator=distributed_coordinator,
            config=distributed_config,
        )
        app.state.distributed_coordinator = distributed_coordinator
        for route in master.routes:
            app.routes.append(route)
    return app


app = create_app()
