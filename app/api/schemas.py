from pydantic import BaseModel, field_validator


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