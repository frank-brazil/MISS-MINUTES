from fastapi import FastAPI

from app.api.router import router
from app.core.ai import AIModel
from app.core.orchestrator import Orchestrator
from app.distributed.httpapi import create_master_app
from app.memory.base import Memory
from app.runtime.runtime import MissMinutesRuntime
from app.security.manager import SecurityManager


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
    app = FastAPI(
        title="MISSMINUTES",
        version="0.1.0",
        description="Personal intelligent AI computer agent",
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
