import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_orchestrator, get_runtime
from app.api.schemas import (
    HealthResponse,
    RuntimeStatusResponse,
    TaskCancelResponse,
    TaskRequest,
    VoiceSessionRequest,
    VoiceSessionResponse,
)
from app.core.orchestrator import OrchestrationResult, Orchestrator
from app.core.task import Task
from app.runtime.runtime import MissMinutesRuntime

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


@router.get("/runtime/status", response_model=RuntimeStatusResponse)
async def runtime_status(
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> RuntimeStatusResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not available")
    report = runtime.capabilities.health_report(
        ready=runtime.ready,
        request_count=runtime.request_count,
    )
    return RuntimeStatusResponse(
        ready=report.ready,
        uptime_seconds=report.uptime_seconds,
        request_count=report.request_count,
        capabilities=runtime.capabilities.all_capabilities(),
    )


@router.post("/voice/session", response_model=VoiceSessionResponse)
async def voice_session(
    request: VoiceSessionRequest,
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> VoiceSessionResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not available")
    result = await runtime.handle_voice(request.audio)
    return VoiceSessionResponse(
        request_id=result.request_id,
        success=result.success,
        text_response=result.text_response,
        error=result.error,
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(
    task_id: str,
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> TaskCancelResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not available")
    return TaskCancelResponse(
        task_id=task_id,
        cancelled=False,
        message="Cancellation not yet supported for in-flight tasks",
    )
