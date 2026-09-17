import asyncio

import pytest
from app.voice.language import (
    ConversationLanguage,
    LanguageDetectionResult,
    LanguageDetector,
    LanguageLabel,
    LanguageMode,
    LanguagePreference,
    ResponseStyle,
)
from pydantic import ValidationError


class SampleLanguageDetector(LanguageDetector):
    name = "sample-language-detector"
    description = "A sample language detector implementation for tests."

    async def detect(self, text: str) -> LanguageDetectionResult:
        if not text.strip():
            return LanguageDetectionResult.unknown()
        return LanguageDetectionResult.detected(
            LanguageLabel.ENGLISH,
            confidence=0.9,
            languages=(LanguageLabel.ENGLISH,),
        )


def detection(label: LanguageLabel, *, confidence: float = 0.9) -> LanguageDetectionResult:
    if label is LanguageLabel.UNKNOWN:
        return LanguageDetectionResult.unknown()
    return LanguageDetectionResult.detected(label, confidence=confidence, languages=(label,))


def test_language_label_values() -> None:
    assert LanguageLabel.ENGLISH == "english"
    assert LanguageLabel.HINDI == "hindi"
    assert LanguageLabel.HINGLISH == "hinglish"
    assert LanguageLabel.URDU == "urdu"
    assert LanguageLabel.MIXED == "mixed"
    assert LanguageLabel.UNKNOWN == "unknown"


def test_language_detector_is_abstract() -> None:
    with pytest.raises(TypeError):
        LanguageDetector()


def test_language_detector_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingName(LanguageDetector):
            description = "missing name"

            async def detect(self, text: str) -> LanguageDetectionResult:
                return LanguageDetectionResult.unknown()

    with pytest.raises(TypeError, match="description"):

        class MissingDescription(LanguageDetector):
            name = "missing-description"

            async def detect(self, text: str) -> LanguageDetectionResult:
                return LanguageDetectionResult.unknown()


def test_concrete_detector_satisfies_interface() -> None:
    detector = SampleLanguageDetector()
    assert detector.name == "sample-language-detector"
    assert detector.description
    result = asyncio.run(detector.detect("hello world"))
    assert result.label is LanguageLabel.ENGLISH


def test_unknown_result_defaults() -> None:
    result = LanguageDetectionResult.unknown()
    assert result.label is LanguageLabel.UNKNOWN
    assert result.confidence is None
    assert result.languages == ()
    assert result.is_mixed is False


def test_detected_result_fields() -> None:
    result = LanguageDetectionResult.detected(
        LanguageLabel.HINDI,
        confidence=0.95,
        languages=(LanguageLabel.HINDI,),
    )
    assert result.label is LanguageLabel.HINDI
    assert result.confidence == 0.95
    assert result.languages == (LanguageLabel.HINDI,)
    assert result.is_mixed is False


def test_unknown_rejects_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        LanguageDetectionResult.detected(LanguageLabel.UNKNOWN, confidence=0.5)


def test_unknown_rejects_languages() -> None:
    with pytest.raises(ValidationError, match="languages"):
        LanguageDetectionResult.detected(LanguageLabel.UNKNOWN, languages=(LanguageLabel.ENGLISH,))


def test_unknown_rejects_mixed() -> None:
    with pytest.raises(ValidationError, match="mixed"):
        LanguageDetectionResult.detected(LanguageLabel.UNKNOWN, is_mixed=True)


def test_mixed_factory() -> None:
    result = LanguageDetectionResult.mixed(LanguageLabel.HINDI, LanguageLabel.ENGLISH)
    assert result.label is LanguageLabel.MIXED
    assert result.confidence == 0.7
    assert result.languages == (LanguageLabel.HINDI, LanguageLabel.ENGLISH)
    assert result.is_mixed is True


def test_mixed_label_requires_is_mixed() -> None:
    with pytest.raises(ValidationError, match="is_mixed"):
        LanguageDetectionResult.detected(
            LanguageLabel.MIXED,
            languages=(LanguageLabel.HINDI, LanguageLabel.ENGLISH),
        )


def test_mixed_label_requires_two_languages() -> None:
    with pytest.raises(ValidationError, match="two languages"):
        LanguageDetectionResult.detected(
            LanguageLabel.MIXED,
            is_mixed=True,
            languages=(LanguageLabel.HINDI,),
        )


def test_mixed_flag_requires_two_languages() -> None:
    with pytest.raises(ValidationError, match="two languages"):
        LanguageDetectionResult.detected(
            LanguageLabel.ENGLISH,
            is_mixed=True,
            languages=(LanguageLabel.ENGLISH,),
        )


def test_label_must_appear_in_languages() -> None:
    with pytest.raises(ValidationError, match="present in languages"):
        LanguageDetectionResult.detected(
            LanguageLabel.ENGLISH,
            languages=(LanguageLabel.HINDI,),
        )


def test_rejects_non_concrete_language_entries() -> None:
    with pytest.raises(ValidationError, match="concrete"):
        LanguageDetectionResult.detected(
            LanguageLabel.MIXED,
            is_mixed=True,
            languages=(LanguageLabel.MIXED, LanguageLabel.ENGLISH),
        )
    with pytest.raises(ValidationError, match="concrete"):
        LanguageDetectionResult.detected(
            LanguageLabel.MIXED,
            is_mixed=True,
            languages=(LanguageLabel.UNKNOWN, LanguageLabel.HINDI),
        )


def test_rejects_duplicate_languages() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        LanguageDetectionResult.detected(
            LanguageLabel.MIXED,
            is_mixed=True,
            languages=(LanguageLabel.HINDI, LanguageLabel.HINDI),
        )


def test_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        LanguageDetectionResult.detected(LanguageLabel.ENGLISH, confidence=1.5)
    with pytest.raises(ValidationError, match="confidence"):
        LanguageDetectionResult.detected(LanguageLabel.ENGLISH, confidence=-0.1)


def test_language_mode_values() -> None:
    assert LanguageMode.AUTO == "auto"
    assert LanguageMode.EXPLICIT == "explicit"


def test_preference_defaults_to_auto() -> None:
    preference = LanguagePreference()
    assert preference.mode is LanguageMode.AUTO
    assert preference.explicit is None


def test_explicit_preference_requires_label() -> None:
    with pytest.raises(ValidationError, match="label"):
        LanguagePreference(mode=LanguageMode.EXPLICIT)


def test_explicit_preference_rejects_unknown_or_mixed() -> None:
    with pytest.raises(ValidationError, match="english, hindi"):
        LanguagePreference(mode=LanguageMode.EXPLICIT, explicit=LanguageLabel.UNKNOWN)
    with pytest.raises(ValidationError, match="english, hindi"):
        LanguagePreference(mode=LanguageMode.EXPLICIT, explicit=LanguageLabel.MIXED)


def test_explicit_language_factory() -> None:
    preference = LanguagePreference.explicit_language(LanguageLabel.HINGLISH)
    assert preference.mode is LanguageMode.EXPLICIT
    assert preference.explicit is LanguageLabel.HINGLISH


def test_explicit_language_factory_rejects_unknown_and_mixed() -> None:
    with pytest.raises(ValueError, match="english, hindi"):
        LanguagePreference.explicit_language(LanguageLabel.UNKNOWN)
    with pytest.raises(ValueError, match="english, hindi"):
        LanguagePreference.explicit_language(LanguageLabel.MIXED)


def test_response_style_defaults() -> None:
    style = ResponseStyle(label=LanguageLabel.ENGLISH, confidence=0.8)
    assert style.label is LanguageLabel.ENGLISH
    assert style.confidence == 0.8
    assert style.explicit is False
    assert style.preserve_mixed is False


def test_guidance_for_concrete_labels() -> None:
    for label in (LanguageLabel.ENGLISH, LanguageLabel.HINDI, LanguageLabel.URDU):
        style = ResponseStyle(label=label)
        assert style.guidance
        assert label.value in style.guidance.lower()


def test_guidance_for_unknown() -> None:
    style = ResponseStyle(label=LanguageLabel.UNKNOWN)
    assert "best fits" in style.guidance


def test_guidance_when_preserving_mixed() -> None:
    style = ResponseStyle(
        label=LanguageLabel.HINGLISH,
        preserve_mixed=True,
    )
    assert "mixed-language" in style.guidance
    assert "forcing it into a single language" in style.guidance


def test_guidance_for_mixed_label() -> None:
    style = ResponseStyle(label=LanguageLabel.MIXED)
    assert "mixed-language" in style.guidance


def test_response_style_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        ResponseStyle(label=LanguageLabel.ENGLISH, confidence=2.0)


def test_conversation_tracker_default_preference() -> None:
    tracker = ConversationLanguage()
    assert tracker.preference.mode is LanguageMode.AUTO
    assert tracker.latest_style is None


def test_conversation_tracker_auto_follows_detection() -> None:
    tracker = ConversationLanguage()
    style = tracker.update(detection(LanguageLabel.HINGLISH, confidence=0.7))
    assert style.label is LanguageLabel.HINGLISH
    assert style.explicit is False
    assert style.preserve_mixed is True
    assert style.confidence == 0.7
    assert tracker.latest_style is style


def test_conversation_tracker_preserves_context_in_unknown_early() -> None:
    tracker = ConversationLanguage()
    style = tracker.update(LanguageDetectionResult.unknown())
    assert style.label is LanguageLabel.UNKNOWN
    assert style.explicit is False


def test_conversation_tracker_reuses_latest_style_on_unknown() -> None:
    tracker = ConversationLanguage()
    first = tracker.update(detection(LanguageLabel.HINGLISH))
    second = tracker.update(LanguageDetectionResult.unknown())
    assert second is first
    assert second.label is LanguageLabel.HINGLISH


def test_language_switching_within_one_conversation() -> None:
    tracker = ConversationLanguage()
    tracker.update(detection(LanguageLabel.ENGLISH))
    tracker.update(detection(LanguageLabel.HINGLISH))
    style = tracker.update(detection(LanguageLabel.ENGLISH))
    assert style.label is LanguageLabel.ENGLISH
    assert style.explicit is False
    assert tracker.latest_style is style


def test_fallback_remembers_most_recent_not_original() -> None:
    tracker = ConversationLanguage()
    tracker.update(detection(LanguageLabel.ENGLISH))
    tracker.update(detection(LanguageLabel.HINGLISH))
    fallback = tracker.update(LanguageDetectionResult.unknown())
    assert fallback.label is LanguageLabel.HINGLISH


def test_conversation_context_is_not_split_by_language() -> None:
    tracker = ConversationLanguage()
    tracker.update(detection(LanguageLabel.ENGLISH))
    tracker.update(detection(LanguageLabel.HINDI))
    tracker.update(detection(LanguageLabel.URDU))
    assert tracker.latest_style is not None
    assert tracker.latest_style.label is LanguageLabel.URDU


def test_explicit_preference_ignores_detection_label() -> None:
    preference = LanguagePreference.explicit_language(LanguageLabel.URDU)
    tracker = ConversationLanguage(preference=preference)
    style = tracker.update(detection(LanguageLabel.ENGLISH, confidence=0.4))
    assert style.label is LanguageLabel.URDU
    assert style.explicit is True
    assert style.confidence == 0.4


def test_explicit_hinglish_sets_preserve_mixed() -> None:
    preference = LanguagePreference.explicit_language(LanguageLabel.HINGLISH)
    tracker = ConversationLanguage(preference=preference)
    style = tracker.update(detection(LanguageLabel.ENGLISH))
    assert style.label is LanguageLabel.HINGLISH
    assert style.preserve_mixed is True


def test_explicit_mode_without_label_raises_on_construction() -> None:
    with pytest.raises(ValidationError, match="label"):
        LanguagePreference(mode=LanguageMode.EXPLICIT, explicit=None)


def test_conversation_tracker_logs_metadata_safely() -> None:
    tracker = ConversationLanguage()
    style = tracker.update(detection(LanguageLabel.HINDI, confidence=0.9))
    assert style.label is LanguageLabel.HINDI
