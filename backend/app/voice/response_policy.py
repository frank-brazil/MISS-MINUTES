"""Spoken response shaping for voice turns.

Decides how each generated reply is turned into audible speech: which
language, voice, and speaking pace to use, and whether the reply is short
(concise). Policies are pure and deterministic so behavior is predictable.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, field_validator

from app.voice.language import LanguageLabel, ResponseStyle


class SpokenResponseProfile(BaseModel):
    """Rendering choices for one spoken response."""

    language: str | None = None
    voice: str | None = None
    speaking_speed: float = 1.0
    short_response: bool = False

    @field_validator("speaking_speed")
    @classmethod
    def _speed_in_range(cls, value: float) -> float:
        if not 0.25 <= value <= 4.0:
            raise ValueError("speaking_speed must be between 0.25 and 4.0")
        return value


_DEFAULT_LANGUAGE_MAP: dict[LanguageLabel, str | None] = {
    LanguageLabel.ENGLISH: "en",
    LanguageLabel.HINDI: "hi",
    LanguageLabel.HINGLISH: "en",
    LanguageLabel.URDU: "ur",
    LanguageLabel.MIXED: None,
    LanguageLabel.UNKNOWN: None,
}


class VoiceResponsePolicy(ABC):
    """Interface for deriving a spoken rendering profile per turn."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    def profile_for(
        self,
        *,
        text: str,
        style: ResponseStyle | None,
        response_text: str,
    ) -> SpokenResponseProfile:
        raise NotImplementedError


class DefaultVoiceResponsePolicy(VoiceResponsePolicy):
    """Deterministic default response policy.

    Language follows the current response style; short replies are spoken a
    little faster and marked as short. All logic is local and constant-time.
    """

    name = "default-voice-response-policy"
    description = "Deterministic default spoken response policy."

    def __init__(
        self,
        *,
        voice: str | None = None,
        language_map: Mapping[LanguageLabel, str | None] | None = None,
        short_response_threshold_chars: int = 40,
        short_speaking_speed: float = 1.2,
        normal_speaking_speed: float = 1.0,
    ) -> None:
        if short_response_threshold_chars < 1:
            raise ValueError("short_response_threshold_chars must be positive")
        for speed in (short_speaking_speed, normal_speaking_speed):
            if not 0.25 <= speed <= 4.0:
                raise ValueError("speaking speed must be between 0.25 and 4.0")
        self._voice = voice
        self._language_map = dict(language_map or _DEFAULT_LANGUAGE_MAP)
        self._short_threshold = short_response_threshold_chars
        self._short_speed = short_speaking_speed
        self._normal_speed = normal_speaking_speed
        self._logger = logging.getLogger(__name__)

    def profile_for(
        self,
        *,
        text: str,
        style: ResponseStyle | None,
        response_text: str,
    ) -> SpokenResponseProfile:
        label = style.label if style is not None else LanguageLabel.UNKNOWN
        language = self._language_map.get(label)
        short = len(response_text.strip()) <= self._short_threshold
        profile = SpokenResponseProfile(
            language=language,
            voice=self._voice,
            speaking_speed=self._short_speed if short else self._normal_speed,
            short_response=short,
        )
        self._logger.info(
            "Spoken profile derived: language=%s short=%s speed=%s",
            profile.language,
            profile.short_response,
            profile.speaking_speed,
        )
        return profile
