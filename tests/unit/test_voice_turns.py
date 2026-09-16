import time

import pytest

from app.voice.language import (
    LanguageDetectionResult,
    LanguageLabel,
    ResponseStyle,
)
from app.voice.turns import (
    ConversationTurnKind,
    ConversationTurnManager,
)


def _detection(label: LanguageLabel) -> LanguageDetectionResult:
    return LanguageDetectionResult.detected(label, confidence=0.9, languages=(label,))


def _style(label: LanguageLabel) -> ResponseStyle:
    return ResponseStyle(label=label)


class _Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def test_manager_first_turn_is_first_kind() -> None:
    manager = ConversationTurnManager(now_fn=time.time)
    turn = manager.begin_turn(
        "s1", text="hello", detection=_detection(LanguageLabel.ENGLISH), now=1.0
    )
    assert turn.kind is ConversationTurnKind.FIRST
    assert turn.continuation is False
    assert turn.turn_id == 1
    assert turn.audio_ref == "audio:s1/1"
    assert turn.label is LanguageLabel.ENGLISH
    assert turn.style is None
    assert manager.latest_turn("s1") is turn


def test_manager_continuation_within_window() -> None:
    manager = ConversationTurnManager(
        continuation_window_seconds=8.0, now_fn=time.time
    )
    manager.begin_turn(
        "s1", text="first", detection=_detection(LanguageLabel.ENGLISH), now=10.0
    )
    turn = manager.begin_turn(
        "s1", text="second", detection=_detection(LanguageLabel.ENGLISH), now=12.0
    )
    assert turn.kind is ConversationTurnKind.CONTINUATION
    assert turn.continuation is True


def test_manager_follow_up_outside_window() -> None:
    manager = ConversationTurnManager(continuation_window_seconds=4.0)
    manager.begin_turn(
        "s1", text="first", detection=_detection(LanguageLabel.ENGLISH), now=10.0
    )
    turn = manager.begin_turn(
        "s1", text="second", detection=_detection(LanguageLabel.ENGLISH), now=20.0
    )
    assert turn.kind is ConversationTurnKind.FOLLOW_UP
    assert turn.continuation is False


def test_manager_marker_without_recent_turn_is_continuation() -> None:
    manager = ConversationTurnManager(continuation_window_seconds=1.0)
    manager.begin_turn(
        "s1", text="fix laptop", detection=_detection(LanguageLabel.HINGLISH), now=10.0
    )
    turn = manager.begin_turn(
        "s1", text="and open browser", detection=_detection(LanguageLabel.HINGLISH), now=50.0
    )
    assert turn.continuation is True
    assert turn.kind is ConversationTurnKind.CONTINUATION


def test_manager_complete_turn_sets_fields() -> None:
    manager = ConversationTurnManager(now_fn=time.time)
    turn = manager.begin_turn(
        "s1", text="hello", detection=_detection(LanguageLabel.ENGLISH), now=5.0
    )
    completed = manager.complete_turn(
        turn.turn_id, response_text="Hi!", success=True, now=6.0
    )
    assert completed.success is True
    assert completed.response_text == "Hi!"
    assert completed.completed_at == 6.0
    assert manager.latest_turn("s1").completed_at == 6.0


def test_manager_complete_unknown_turn_raises() -> None:
    manager = ConversationTurnManager()
    with pytest.raises(KeyError):
        manager.complete_turn(123, now=1.0)


def test_manager_begin_blank_is_rejected() -> None:
    manager = ConversationTurnManager()
    with pytest.raises(ValueError):
        manager.begin_turn(
            "s1", text="  ", detection=_detection(LanguageLabel.ENGLISH), now=1.0
        )


def test_manager_preserves_style_and_metadata() -> None:
    manager = ConversationTurnManager(now_fn=time.time)
    turn = manager.begin_turn(
        "s1",
        text="mera laptop",
        detection=_detection(LanguageLabel.HINGLISH),
        style=_style(LanguageLabel.HINGLISH),
        audio_bytes=128,
        now=1.0,
    )
    assert turn.style == _style(LanguageLabel.HINGLISH)
    assert turn.audio_bytes == 128
    assert turn.transcription == "mera laptop"


def test_manager_is_continuation_helper() -> None:
    manager = ConversationTurnManager(continuation_window_seconds=5.0)
    first = manager.begin_turn(
        "s1", text="first", detection=_detection(LanguageLabel.ENGLISH), now=1.0
    )
    assert manager.is_continuation(first, "and more", now=3.0) is True
    assert manager.is_continuation(first, "unrelated", now=50.0) is False
    assert manager.is_continuation(None, "anything", now=1.0) is False


def test_manager_turns_per_session_and_ids_monotonic() -> None:
    manager = ConversationTurnManager(now_fn=time.time)
    manager.begin_turn("a", text="one", detection=_detection(LanguageLabel.ENGLISH), now=1.0)
    manager.begin_turn("b", text="two", detection=_detection(LanguageLabel.ENGLISH), now=2.0)
    manager.begin_turn("a", text="three", detection=_detection(LanguageLabel.ENGLISH), now=3.0)
    session_a = manager.turns("a")
    assert [turn.turn_id for turn in session_a] == [1, 3]
    assert manager.turns("b")[0].turn_id == 2
    assert manager.latest_turn("missing") is None
