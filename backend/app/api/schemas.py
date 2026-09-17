from pydantic import BaseModel, Field, field_validator


class TaskRequest(BaseModel):
    description: str

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v


class HealthResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class ChatResponse(BaseModel):
    message: str
    status: str
    task_id: str | None = None


class VoiceSessionRequest(BaseModel):
    audio: bytes = Field(min_length=1, description="Audio data (raw bytes)")
    format: str = Field(default="wav", description="Audio format")
    language_hint: str | None = Field(default=None, description="Optional language hint")

    @field_validator("format")
    @classmethod
    def _format_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("format must not be blank")
        return v


class VoiceSessionResponse(BaseModel):
    request_id: str
    success: bool
    text_response: str | None = None
    error: str | None = None


class RuntimeStatusResponse(BaseModel):
    ready: bool
    uptime_seconds: float
    request_count: int
    capabilities: dict[str, bool]


class TaskCancelResponse(BaseModel):
    task_id: str
    cancelled: bool
    message: str


class AvatarStateResponse(BaseModel):
    state: str
    expression: str
    running: bool
