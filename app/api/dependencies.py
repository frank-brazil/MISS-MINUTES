from fastapi import Request

from app.core.orchestrator import Orchestrator


def get_orchestrator(request: Request) -> Orchestrator:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise RuntimeError("Orchestrator is not available on the application state")
    return orchestrator


def get_runtime(request: Request):
    """Return the MissMinutesRuntime if available, else None."""
    return getattr(request.app.state, "runtime", None)
