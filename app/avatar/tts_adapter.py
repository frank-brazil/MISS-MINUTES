"""TTS-to-lip-sync adapter.

This is the explicit, read-only boundary between the existing voice layer and
the avatar lip-sync engine (mirroring :mod:`app.avatar.voice_adapter`): it turns
a ``TextToSpeechResult`` into a :class:`LipSyncTiming`. It never calls a TTS
provider and never modifies the voice pipeline.

``TextToSpeechResult`` only exposes a total ``duration`` (not per-sound data),
so the adapter scales approximate per-character timing to that measured total
and keeps ``TimingAccuracy.APPROXIMATE`` — unit boundaries are estimates even
when the overall duration came from a real synthesis. Without a result the
timing is a pure text estimate.
"""

from typing import Callable

from app.avatar.lipsync import (
    ApproximateLipSyncProvider,
    LipSyncController,
    LipSyncProvider,
    LipSyncTiming,
    SpeechUnit,
    TimingAccuracy,
)
from app.voice.base import TextToSpeechResult


class TTSLipSyncAdapter:
    """Maps a ``TextToSpeechResult`` (or plain text) to avatar lip timing."""

    def __init__(
        self,
        provider: LipSyncProvider | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._provider = provider or ApproximateLipSyncProvider()
        self._now_fn = now_fn

    @property
    def provider(self) -> LipSyncProvider:
        return self._provider

    def timing_for(
        self,
        text: str,
        result: TextToSpeechResult | None = None,
    ) -> LipSyncTiming:
        """Lip timing for ``text``, optionally anchored to a TTS result.

        When the result carries a measured total duration, approximate unit
        timing is rescaled to match it; otherwise a pure text estimate is
        returned.
        """
        base = self._provider.timing_for(text)
        if result is None or not result.success:
            return base
        measured = result.duration
        if measured is None or measured.total_seconds() <= 0:
            return base
        total = measured.total_seconds()
        if base.duration_seconds <= 0 or not base.units:
            return LipSyncTiming(
                accuracy=TimingAccuracy.APPROXIMATE,
                units=(),
                duration_seconds=total,
            )
        ratio = total / base.duration_seconds
        units = tuple(
            SpeechUnit(
                symbol=unit.symbol,
                start_time=unit.start_time * ratio,
                duration=unit.duration * ratio,
            )
            for unit in base.units
        )
        return LipSyncTiming(
            accuracy=TimingAccuracy.APPROXIMATE,
            units=units,
            duration_seconds=total,
        )

    def controller(
        self,
        text: str,
        result: TextToSpeechResult | None = None,
        *,
        at: float | None = None,
    ) -> LipSyncController:
        """A ready-to-play :class:`LipSyncController` seeded with the timing."""
        controller = LipSyncController(self._provider, now_fn=self._now_fn)
        controller.start(text, timing=self.timing_for(text, result), at=at)
        return controller
