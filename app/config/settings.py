"""Configuration loading for MISSMINUTES.

Loads configuration from a TOML file and overlays environment variables.
Secrets are never stored in the config object — they are read from
environment variables at provider construction time.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.config.schema import (
    AIConfig,
    AvatarConfig,
    BrowserConfig,
    DistributedConfigSchema,
    FilesystemConfig,
    MissMinutesConfig,
    SecurityConfig,
    VisionConfig,
    VoiceConfig,
)

logger = logging.getLogger(__name__)

_ENV_PREFIX = "MISSMINUTES_"

_ENV_MAP: dict[str, tuple[str, type]] = {
    # AI
    "MISSMINUTES_AI_PROVIDER": ("ai.provider", str),
    "MISSMINUTES_AI_MODEL": ("ai.model", str),
    "MISSMINUTES_AI_TIMEOUT": ("ai.timeout_seconds", float),
    # Voice
    "MISSMINUTES_VOICE_ENABLED": ("voice.enabled", bool),
    "MISSMINUTES_STT_PROVIDER": ("voice.stt_provider", str),
    "MISSMINUTES_TTS_PROVIDER": ("voice.tts_provider", str),
    "MISSMINUTES_WAKE_WORD": ("voice.wake_word", str),
    "MISSMINUTES_LANGUAGE_MODE": ("voice.language_mode", str),
    "MISSMINUTES_CONTINUOUS_LISTENING": ("voice.continuous_listening", bool),
    "MISSMINUTES_LOCAL_ONLY": ("voice.local_only", bool),
    # Avatar
    "MISSMINUTES_AVATAR_ENABLED": ("avatar.enabled", bool),
    "MISSMINUTES_AVATAR_THEME": ("avatar.theme", str),
    "MISSMINUTES_AVATAR_WINDOW": ("avatar.window_behavior", str),
    # Security
    "MISSMINUTES_SECURITY_MODE": ("security.policy_mode", str),
    "MISSMINUTES_CONFIRMATION_REQUIRED": ("security.confirmation_required", bool),
    "MISSMINUTES_AUDIT_ENABLED": ("security.audit_enabled", bool),
    "MISSMINUTES_AUDIT_MAX_EVENTS": ("security.audit_max_events", int),
    # Distributed
    "MISSMINUTES_DISTRIBUTED_ENABLED": ("distributed.enabled", bool),
    "MISSMINUTES_MASTER_HOST": ("distributed.master_host", str),
    "MISSMINUTES_MASTER_PORT": ("distributed.master_port", int),
    "MISSMINUTES_MAX_RETRIES": ("distributed.max_retries", int),
    "MISSMINUTES_MAX_CONCURRENT_DISPATCH": ("distributed.max_concurrent_dispatch", int),
    "MISSMINUTES_DISPATCH_TIMEOUT": ("distributed.dispatch_timeout", float),
    # Browser
    "MISSMINUTES_BROWSER_ENABLED": ("browser.enabled", bool),
    # Filesystem
    "MISSMINUTES_FILESYSTEM_ROOTS": ("filesystem.allowed_roots", str),
    # Vision
    "MISSMINUTES_VISION_ENABLED": ("vision.enabled", bool),
    "MISSMINUTES_VISION_PROVIDER": ("vision.provider", str),
}


def _set_nested(data: dict, dotpath: str, value: object) -> None:
    """Set a value in a nested dict using a dotted path like 'a.b.c'."""
    keys = dotpath.split(".")
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    data[keys[-1]] = value


def _parse_bool(value: str) -> bool:
    return value.lower() in ("1", "true", "yes")


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config(path: Path | str | None = None) -> MissMinutesConfig:
    """Load configuration from a TOML file with environment variable overrides.

    Parameters
    ----------
    path:
        Path to a TOML configuration file. When ``None`` the loader tries
        ``config/missminutes.toml`` relative to the working directory.

    Environment variables matching ``MISSMINUTES_*`` override file values.
    """
    raw: dict = {}

    resolved = Path(path) if path is not None else Path("config/missminutes.toml")
    if resolved.is_file():
        try:
            import tomllib

            with open(resolved, "rb") as fh:
                raw = tomllib.load(fh)
            logger.info("Loaded configuration from %s", resolved)
        except Exception:
            logger.warning(
                "Failed to load TOML config from %s, using defaults", resolved
            )
    else:
        logger.info("No config file at %s, using defaults + env vars", resolved)

    # Overlay environment variables
    for env_key, (dotpath, type_fn) in _ENV_MAP.items():
        env_val = os.environ.get(env_key)
        if env_val is None:
            continue
        try:
            if type_fn is bool:
                parsed: object = _parse_bool(env_val)
            elif type_fn is list:
                parsed = _parse_list(env_val)
            else:
                parsed = type_fn(env_val)
            _set_nested(raw, dotpath, parsed)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid value for %s: %s (expected %s)",
                env_key,
                env_val,
                type_fn.__name__,
            )

    # Build sub-configs, ignoring unknown keys
    ai = AIConfig(**raw.get("ai", {}))
    voice = VoiceConfig(**raw.get("voice", {}))
    avatar = AvatarConfig(**raw.get("avatar", {}))
    security = SecurityConfig(**raw.get("security", {}))
    distributed = DistributedConfigSchema(**raw.get("distributed", {}))
    browser = BrowserConfig(**raw.get("browser", {}))
    filesystem = FilesystemConfig(**raw.get("filesystem", {}))
    vision = VisionConfig(**raw.get("vision", {}))

    return MissMinutesConfig(
        ai=ai,
        voice=voice,
        avatar=avatar,
        security=security,
        distributed=distributed,
        browser=browser,
        filesystem=filesystem,
        vision=vision,
    )
