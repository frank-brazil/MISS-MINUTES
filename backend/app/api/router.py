import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_orchestrator, get_runtime
from app.api.schemas import (
    AvatarStateResponse,
    ChatRequest,
    ChatResponse,
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


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/info")
async def api_info() -> dict[str, str]:
    return {
        "name": "MISSMINUTES",
        "version": "0.1.0",
        "status": "running",
        "description": "Personal intelligent AI computer agent",
    }


@router.post("/api/chat", response_model=ChatResponse)
async def api_chat(
    request: ChatRequest,
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> ChatResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not available")
    result = await runtime.handle_text(request.message)
    if result.success:
        return ChatResponse(
            message=result.text_response or "No response generated.",
            status="success",
            task_id=str(result.task_id),
        )
    else:
        return ChatResponse(
            message=result.error or "Request failed.",
            status="error",
            task_id=str(result.task_id),
        )


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


@router.get("/api/avatar/state", response_model=AvatarStateResponse)
async def avatar_state(
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> AvatarStateResponse:
    if runtime is None or runtime.avatar_controller is None:
        return AvatarStateResponse(state="idle", expression="neutral", running=False)
    controller = runtime.avatar_controller
    return AvatarStateResponse(
        state=controller.state.value,
        expression=controller.expression,
        running=controller.running,
    )


@router.post("/api/avatar/signal")
async def avatar_signal(
    signal: str,
    runtime: MissMinutesRuntime | None = Depends(get_runtime),
) -> dict[str, str]:
    if runtime is None or runtime.avatar_controller is None:
        raise HTTPException(status_code=503, detail="Avatar not available")
    from app.avatar.controller import AvatarSignal

    try:
        sig = AvatarSignal(signal)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown signal: {signal}. Valid: {[s.value for s in AvatarSignal]}",
        )
    success = runtime.avatar_controller.handle(sig)
    return {"signal": signal, "accepted": str(success)}


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
