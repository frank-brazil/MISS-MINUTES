"""Distributed layer configuration.

Values come from the environment (``MISSMINUTES_*``) with safe local-dev
defaults.  Secrets are **never hard-coded** in source: the authentication
token defaults to ``None`` and must be supplied via configuration.

Resource values here are scheduling metadata only; they make no claim about
measured performance.
"""

import os
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

BIND_HOST = "127.0.0.1"
MASTER_BIND_PORT = 8100
WORKER_BIND_PORT = 8200
HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2
MAX_CONCURRENT_DISPATCH = 4
DISPATCH_TIMEOUT_SECONDS = 30.0

_ENV_PREFIX = "MISSMINUTES_"


class DistributedConfig(BaseModel):
    """Shared configuration for master and worker processes."""

    model_config = ConfigDict(validate_assignment=True)

    master_bind_host: str = BIND_HOST
    master_bind_port: int = MASTER_BIND_PORT
    worker_bind_host: str = BIND_HOST
    worker_bind_port: int = WORKER_BIND_PORT
    heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS
    heartbeat_timeout_seconds: float = HEARTBEAT_TIMEOUT_SECONDS
    max_retries: int = MAX_RETRIES
    max_concurrent_dispatch: int = MAX_CONCURRENT_DISPATCH
    dispatch_timeout_seconds: float = DISPATCH_TIMEOUT_SECONDS
    auth_token: str | None = None

    #: Number of heartbeat misses before a worker is considered stale (used in
    #: documentation and messaging only; the timeout value is authoritative).
    heartbeat_miss_threshold: ClassVar[int] = 3

    @field_validator("master_bind_host", "worker_bind_host")
    @classmethod
    def _host_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bind host must not be blank")
        return value

    @field_validator("master_bind_port", "worker_bind_port")
    @classmethod
    def _port_in_range(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator(
        "heartbeat_interval_seconds",
        "heartbeat_timeout_seconds",
        "dispatch_timeout_seconds",
    )
    @classmethod
    def _positive_durations(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("durations must be positive")
        return value

    @field_validator("max_retries")
    @classmethod
    def _retries_not_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retries must not be negative")
        return value

    @field_validator("max_concurrent_dispatch")
    @classmethod
    def _concurrency_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_concurrent_dispatch must be at least 1")
        return value

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "DistributedConfig":
        """Build a config from the environment (``os.environ`` by default).

        The authentication token is read only from configuration; it is never
        part of WorkerInfo or any response model.
        """
        source = os.environ if env is None else env
        kwargs = {
            "master_bind_host": source.get(f"{_ENV_PREFIX}MASTER_HOST", BIND_HOST),
            "master_bind_port": int(source.get(f"{_ENV_PREFIX}MASTER_PORT", MASTER_BIND_PORT)),
            "worker_bind_host": source.get(f"{_ENV_PREFIX}WORKER_HOST", BIND_HOST),
            "worker_bind_port": int(source.get(f"{_ENV_PREFIX}WORKER_PORT", WORKER_BIND_PORT)),
            "heartbeat_interval_seconds": float(
                source.get(
                    f"{_ENV_PREFIX}HEARTBEAT_INTERVAL",
                    HEARTBEAT_INTERVAL_SECONDS,
                )
            ),
            "heartbeat_timeout_seconds": float(
                source.get(
                    f"{_ENV_PREFIX}HEARTBEAT_TIMEOUT",
                    HEARTBEAT_TIMEOUT_SECONDS,
                )
            ),
            "max_retries": int(source.get(f"{_ENV_PREFIX}MAX_RETRIES", MAX_RETRIES)),
            "max_concurrent_dispatch": int(
                source.get(
                    f"{_ENV_PREFIX}MAX_CONCURRENT_DISPATCH",
                    MAX_CONCURRENT_DISPATCH,
                )
            ),
            "dispatch_timeout_seconds": float(
                source.get(
                    f"{_ENV_PREFIX}DISPATCH_TIMEOUT",
                    DISPATCH_TIMEOUT_SECONDS,
                )
            ),
            "auth_token": source.get(f"{_ENV_PREFIX}AUTH_TOKEN"),
        }
        return cls(**kwargs)
