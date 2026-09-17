import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, field_validator, model_validator

EXPLICIT_LABELS = frozenset(
    {
        "english",
        "hindi",
        "hinglish",
        "urdu",
    }
)


class LanguageLabel(StrEnum):
    """Supported conversational language and style labels."""

    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"
    URDU = "urdu"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LanguageDetectionResult(BaseModel):
    """Outcome of a language or style detection attempt.

    ``label`` is the dominant chosen label. ``languages`` lists the concrete
    languages that were observed (informative for mixed input). ``unknown``
    results never carry a confidence or a language list: the detector cannot
    even guess, so it says so rather than claiming a number.
    """

    label: LanguageLabel
    confidence: float | None = None
    languages: tuple[LanguageLabel, ...] = ()
    is_mixed: bool = False

    @classmethod
    def detected(
        cls,
        label: LanguageLabel,
        *,
        confidence: float | None = None,
        languages: tuple[LanguageLabel, ...] | None = None,
        is_mixed: bool = False,
    ) -> "LanguageDetectionResult":
        return cls(
            label=label,
            confidence=confidence,
            languages=languages or (),
            is_mixed=is_mixed,
        )

    @classmethod
    def mixed(cls, *languages: LanguageLabel) -> "LanguageDetectionResult":
        return cls(
            label=LanguageLabel.MIXED,
            confidence=0.7,
            languages=tuple(languages),
            is_mixed=True,
        )

    @classmethod
    def unknown(cls) -> "LanguageDetectionResult":
        return cls(label=LanguageLabel.UNKNOWN)

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _validate_coherence(self) -> "LanguageDetectionResult":
        if self.label is LanguageLabel.UNKNOWN:
            if self.confidence is not None:
                raise ValueError("unknown detection cannot carry a confidence")
            if self.languages:
                raise ValueError("unknown detection cannot carry languages")
            if self.is_mixed:
                raise ValueError("unknown detection cannot be mixed")
            return self

        for language in self.languages:
            if language in (LanguageLabel.MIXED, LanguageLabel.UNKNOWN):
                raise ValueError("languages must list concrete languages only")
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("languages must not contain duplicates")

        if self.label is LanguageLabel.MIXED:
            if not self.is_mixed:
                raise ValueError("mixed label requires is_mixed=True")
            if len(self.languages) < 2:
                raise ValueError("mixed detection requires at least two languages")
        if self.is_mixed and len(self.languages) < 2:
            raise ValueError("mixed detection requires at least two languages")
        if (
            self.label is not LanguageLabel.MIXED
            and self.languages
            and self.label not in self.languages
        ):
            raise ValueError("label must be present in languages")
        return self


class LanguageDetector(ABC):
    """Detects the dominant language or style of a message.

    Implementations are interchangeable: a deterministic local detector is
    provided for offline use, and a remote service detector could replace it
    without touching the rest of the voice subsystem. Detectors never claim a
    perfect identification; ``unknown`` is a legitimate, safe answer.
    """

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
    async def detect(self, text: str) -> LanguageDetectionResult:
        raise NotImplementedError


class LanguageMode(StrEnum):
    """How the conversational language preference is resolved."""

    AUTO = "auto"
    EXPLICIT = "explicit"


class LanguagePreference(BaseModel):
    """Typed conversational language preference for one speaker.

    In ``auto`` mode the conversational language follows the detected style of
    each message. In ``explicit`` mode the speaker has chosen a concrete
    language; detection results are advisory only.
    """

    mode: LanguageMode = LanguageMode.AUTO
    explicit: LanguageLabel | None = None

    @classmethod
    def explicit_language(cls, label: LanguageLabel) -> "LanguagePreference":
        if label not in EXPLICIT_LABELS:
            raise ValueError("explicit language must be english, hindi, hinglish, or urdu")
        return cls(mode=LanguageMode.EXPLICIT, explicit=label)

    @model_validator(mode="after")
    def _validate_explicit(self) -> "LanguagePreference":
        if self.mode is LanguageMode.EXPLICIT and self.explicit is None:
            raise ValueError("explicit preference requires a concrete language label")
        if self.explicit is not None and self.explicit not in EXPLICIT_LABELS:
            raise ValueError("explicit language must be english, hindi, hinglish, or urdu")
        return self


_GUIDANCE_BY_LABEL: dict[LanguageLabel, str] = {
    LanguageLabel.ENGLISH: "Reply in English.",
    LanguageLabel.HINDI: "Reply in Hindi using the Devanagari script.",
    LanguageLabel.HINGLISH: "Reply in Hinglish, that is Romanized Hindi mixed naturally with English.",
    LanguageLabel.URDU: "Reply in Urdu using the Arabic script.",
}

_MIXED_GUIDANCE = (
    "Reply naturally, preserving the user's mixed-language style without "
    "forcing it into a single language."
)

_UNKNOWN_GUIDANCE = "Reply using the language or style that best fits the user's message."


class ResponseStyle(BaseModel):
    """Preferred style for the next response, derived from conversation state.

    The response generator uses ``guidance`` to pick a language or mixed style;
    semantic intent is kept separate from presentation, so switching styles
    never reinterprets the underlying task.
    """

    label: LanguageLabel
    confidence: float | None = None
    explicit: bool = False
    preserve_mixed: bool = False

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @property
    def guidance(self) -> str:
        if self.label is LanguageLabel.UNKNOWN:
            return _UNKNOWN_GUIDANCE
        if self.preserve_mixed or self.label is LanguageLabel.MIXED:
            return _MIXED_GUIDANCE
        return _GUIDANCE_BY_LABEL[self.label]


class ConversationLanguage:
    """Tracks the preferred response style for a single conversation.

    The tracker holds exactly one active style. It knows nothing about tasks
    or conversation content, so switching languages mid-conversation keeps the
    surrounding context intact: there are no per-language conversation
    histories to clear or duplicate. In auto mode an ``unknown`` detection
    falls back to the most recently adopted style to maintain continuity.
    """

    def __init__(self, *, preference: LanguagePreference | None = None) -> None:
        self._preference = preference or LanguagePreference()
        self._latest_style: ResponseStyle | None = None
        self._logger = logging.getLogger(__name__)

    @property
    def preference(self) -> LanguagePreference:
        return self._preference

    @property
    def latest_style(self) -> ResponseStyle | None:
        return self._latest_style

    def update(self, detection: LanguageDetectionResult) -> ResponseStyle:
        if self._preference.mode is LanguageMode.EXPLICIT:
            label = self._preference.explicit
            if label is None:
                raise ValueError("explicit language preference requires an explicit label")
            style = ResponseStyle(
                label=label,
                confidence=detection.confidence,
                explicit=True,
                preserve_mixed=label is LanguageLabel.HINGLISH,
            )
        elif detection.label is LanguageLabel.UNKNOWN:
            if self._latest_style is not None:
                style = self._latest_style
            else:
                style = ResponseStyle(label=LanguageLabel.UNKNOWN)
        else:
            style = ResponseStyle(
                label=detection.label,
                confidence=detection.confidence,
                explicit=False,
                preserve_mixed=detection.label in (LanguageLabel.HINGLISH, LanguageLabel.MIXED),
            )
        self._latest_style = style
        self._logger.info(
            "Conversation language updated: label=%s mode=%s explicit=%s",
            style.label.value,
            self._preference.mode.value,
            style.explicit,
        )
        return style
