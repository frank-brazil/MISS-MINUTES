import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_orchestrator
from app.api.schemas import HealthResponse, TaskRequest
from app.core.orchestrator import OrchestrationResult, Orchestrator
from app.core.task import Task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "MISSMINUTES",
        "version": "0.1.0",
        "status": "running",
        "description": "Personal intelligent AI computer agent",
    }


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/tasks", response_model=OrchestrationResult)
async def create_task(
    request: TaskRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> OrchestrationResult:
    task = Task(description=request.description)
    logger.info("Received task request %s", task.task_id)
    result = await orchestrator.execute(task)
    logger.info("Task %s finished with status %s", result.task_id, result.status)
    return result