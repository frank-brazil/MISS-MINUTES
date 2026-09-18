import asyncio

import pytest

from app.voice.language import LanguageDetector, LanguageLabel
from app.voice.local_detector import LocalLanguageDetector

ENGLISH_SAMPLES = (
    "What is the weather today?",
    "hello, how can I help you?",
    "Please open VS Code.",
)

HINDI_SAMPLES = (
    "मेरा नाम राहुल है।",
    "नमस्ते",
)

URDU_SAMPLES = (
    "آپ کیسے ہیں؟",
    "میں ٹھیک ہوں",
)

HINGLISH_SAMPLES = (
    "Mera laptop slow ho gaya hai, can you check what's happening?",
    "Ye code samajh nahi aa raha, explain it simply.",
    "Kal mera exam hai, important topics batao.",
    "kal kya hoga",
)

UNKNOWN_SAMPLES = ("", "   ", "lkjh qwerty zxcv", "1234", "!@# $%^")


def run_detect(text: str):
    return asyncio.run(LocalLanguageDetector().detect(text))


def test_local_detector_satisfies_interface() -> None:
    detector = LocalLanguageDetector()
    assert isinstance(detector, LanguageDetector)
    assert detector.name == "local-language-detector"
    assert detector.description


@pytest.mark.parametrize("sample", ENGLISH_SAMPLES)
def test_detects_english(sample) -> None:
    result = run_detect(sample)
    assert result.label is LanguageLabel.ENGLISH
    assert result.languages == (LanguageLabel.ENGLISH,)
    assert result.is_mixed is False
    assert result.confidence is not None
    assert 0.5 <= result.confidence <= 0.85


@pytest.mark.parametrize("sample", HINDI_SAMPLES)
def test_detects_hindi(sample) -> None:
    result = run_detect(sample)
    assert result.label is LanguageLabel.HINDI
    assert result.languages == (LanguageLabel.HINDI,)
    assert result.confidence == 0.95


@pytest.mark.parametrize("sample", URDU_SAMPLES)
def test_detects_urdu(sample) -> None:
    result = run_detect(sample)
    assert result.label is LanguageLabel.URDU
    assert result.languages == (LanguageLabel.URDU,)
    assert result.confidence == 0.9


@pytest.mark.parametrize("sample", HINGLISH_SAMPLES)
def test_detects_hinglish(sample) -> None:
    result = run_detect(sample)
    assert result.label is LanguageLabel.HINGLISH
    assert result.languages == (LanguageLabel.HINGLISH,)
    assert result.confidence is not None


def test_detects_mixed_devanagari_and_latin() -> None:
    result = run_detect("मेरा laptop slow हो गया है, क्या हुआ?")
    assert result.label is LanguageLabel.MIXED
    assert result.is_mixed is True
    assert result.languages == (LanguageLabel.HINDI, LanguageLabel.ENGLISH)
    assert result.confidence == 0.7


@pytest.mark.parametrize("sample", UNKNOWN_SAMPLES)
def test_detects_unknown(sample) -> None:
    result = run_detect(sample)
    assert result.label is LanguageLabel.UNKNOWN
    assert result.confidence is None


def test_detection_is_repeatable() -> None:
    detector = LocalLanguageDetector()
    sample = "Mera laptop slow ho gaya hai, can you check what's happening?"
    first = asyncio.run(detector.detect(sample))
    second = asyncio.run(detector.detect(sample))
    assert first == second
    assert first.label is LanguageLabel.HINGLISH


def test_detection_never_raises_for_arbitrary_text() -> None:
    detector = LocalLanguageDetector()
    samples = [
        "ßeta óóra ĭçe",
        "🇮🇳 🙏 🚀",
        "Mixed 123 characters, multiple? punctuation!",
        "\u200bzero width",
    ]
    for sample in samples:
        result = asyncio.run(detector.detect(sample))
        assert isinstance(result.label, LanguageLabel)


def test_real_detector_is_interchangeable_with_abstraction() -> None:
    async def use(detector: LanguageDetector) -> str:
        result = await detector.detect("What is the weather today?")
        return result.label.value

    assert asyncio.run(use(LocalLanguageDetector())) == "english"
