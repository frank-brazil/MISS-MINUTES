"""Centralized configuration schema for MISSMINUTES.

All configuration is represented as typed Pydantic models. Secrets (API keys,
auth tokens) are intentionally excluded — they are read from environment
variables at provider construction time, never stored in config objects.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Application-level settings (host, port, logging, environment)."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    environment: str = "development"


class AIConfig(BaseModel):
    """AI model provider settings."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    timeout_seconds: float = Field(default=60.0, gt=0)


class VoiceConfig(BaseModel):
    """Voice pipeline settings."""

    enabled: bool = False
    stt_provider: str = "openai"
    tts_provider: str = "openai"
    wake_word: str = ""
    language_mode: str = "auto"
    continuous_listening: bool = False
    local_only: bool = False


class AvatarConfig(BaseModel):
    """Avatar presentation settings."""

    enabled: bool = False
    theme: str = "default"
    window_behavior: str = "taskbar"


class SecurityConfig(BaseModel):
    """Security policy settings."""

    policy_mode: str = "default"
    confirmation_required: bool = True
    audit_enabled: bool = True
    audit_max_events: int = Field(default=1000, gt=0)


class DistributedConfigSchema(BaseModel):
    """Distributed execution settings."""

    enabled: bool = False
    master_host: str = "127.0.0.1"
    master_port: int = 8100
    # ADD API HERE: MISSMINUTES_AUTH_TOKEN (internal shared secret for master/worker auth)
    auth_token: str = ""
    max_retries: int = Field(default=2, ge=0)
    max_concurrent_dispatch: int = Field(default=4, gt=0)
    dispatch_timeout: float = Field(default=30.0, gt=0)


class BrowserConfig(BaseModel):
    """Browser automation settings."""

    enabled: bool = False
    allowed_domains: list[str] = Field(default_factory=list)


class FilesystemConfig(BaseModel):
    """Filesystem access settings."""

    allowed_roots: list[str] = Field(default_factory=list)


class VisionConfig(BaseModel):
    """Vision/screen understanding settings."""

    enabled: bool = False
    provider: str = "local"


class MissMinutesConfig(BaseModel):
    """Top-level application configuration.

    Loaded from TOML file with environment variable overrides.
    """

    app: AppConfig = Field(default_factory=AppConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    avatar: AvatarConfig = Field(default_factory=AvatarConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    distributed: DistributedConfigSchema = Field(default_factory=DistributedConfigSchema)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
