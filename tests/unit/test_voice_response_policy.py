import pytest
from pydantic import ValidationError

from app.voice.language import LanguageLabel, ResponseStyle
from app.voice.response_policy import (
    DefaultVoiceResponsePolicy,
    SpokenResponseProfile,
    VoiceResponsePolicy,
)


def _style(label: LanguageLabel) -> ResponseStyle:
    return ResponseStyle(label=label)


def test_profile_speed_validation() -> None:
    with pytest.raises(ValidationError):
        SpokenResponseProfile(speaking_speed=9.0)
    SpokenResponseProfile(speaking_speed=1.0)


def test_abstract_policy_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(VoiceResponsePolicy):
            def profile_for(self, **kwargs):
                return SpokenResponseProfile()


def test_default_policy_maps_language_by_style() -> None:
    policy = DefaultVoiceResponsePolicy()
    profile = policy.profile_for(
        text="hello", style=_style(LanguageLabel.HINDI), response_text="आप कैसे हैं?"
    )
    assert profile.language == "hi"
    assert profile.voice is None


def test_default_policy_unknown_style_defaults_to_none() -> None:
    policy = DefaultVoiceResponsePolicy()
    profile = policy.profile_for(
        text="?", style=_style(LanguageLabel.UNKNOWN), response_text="Hmm."
    )
    assert profile.language is None


def test_default_policy_speech_speed_by_length() -> None:
    policy = DefaultVoiceResponsePolicy(
        short_response_threshold_chars=10,
        short_speaking_speed=1.3,
        normal_speaking_speed=1.0,
    )
    short_profile = policy.profile_for(
        text="ok", style=_style(LanguageLabel.ENGLISH), response_text="Sure."
    )
    long_profile = policy.profile_for(
        text="question",
        style=_style(LanguageLabel.ENGLISH),
        response_text="A much longer response than the threshold",
    )
    assert short_profile.short_response is True
    assert short_profile.speaking_speed == 1.3
    assert long_profile.short_response is False
    assert long_profile.speaking_speed == 1.0


def test_default_policy_configurable_voice() -> None:
    policy = DefaultVoiceResponsePolicy(voice="amrita")
    profile = policy.profile_for(
        text="hi", style=_style(LanguageLabel.ENGLISH), response_text="Hi"
    )
    assert profile.voice == "amrita"


def test_default_policy_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError):
        DefaultVoiceResponsePolicy(short_response_threshold_chars=0)