from fastapi import Request

from app.core.orchestrator import Orchestrator


def get_orchestrator(request: Request) -> Orchestrator:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise RuntimeError("Orchestrator is not available on the application state")
    return orchestrator