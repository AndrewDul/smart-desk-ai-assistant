from __future__ import annotations

from modules.devices.audio.output.tts_pipeline import TTSPipeline

import threading
from pathlib import Path

from modules.devices.audio.output.tts_pipeline.cache_queue_mixin import (
    TTSPipelineCacheQueueMixin,
)


class _WarmupProbe(TTSPipelineCacheQueueMixin):
    def __init__(self, cache_dir: Path) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self._cache_warmup_delay_seconds = 0.0
        self._common_cache_phrases = {
            "en": ["Okay."],
            "pl": ["Dobrze."],
        }
        self._stop_requested = threading.Event()
        self._PRIORITY_WARMUP = 3
        self.cache_dir = cache_dir
        self.enqueued: list[tuple[str, str, int]] = []

    def _piper_model_ready(self, lang: str) -> bool:
        return lang in {"en", "pl"}

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        del lang
        return str(text or "").strip()

    def _cached_wav_path(self, text: str, lang: str) -> Path:
        safe_name = text.replace(" ", "_").replace(".", "dot")
        return self.cache_dir / lang / f"{safe_name}.wav"

    def _enqueue_synthesis(self, text: str, lang: str, *, priority: int):
        self.enqueued.append((text, lang, priority))
        return object()

    def _current_time_cache_phrases(self) -> tuple[str, ...]:
        return ("12 34", "12 35", "12 36")


def test_common_cache_warmup_includes_dynamic_short_time_phrases(tmp_path: Path) -> None:
    probe = _WarmupProbe(tmp_path)

    probe._warm_common_cache()

    assert ("12 34", "en", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("12 35", "en", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("12 36", "en", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("12 34", "pl", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("12 35", "pl", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("12 36", "pl", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("Okay.", "en", probe._PRIORITY_WARMUP) in probe.enqueued
    assert ("Dobrze.", "pl", probe._PRIORITY_WARMUP) in probe.enqueued


def test_current_time_cache_phrases_are_short_numeric_and_deduplicated(tmp_path: Path) -> None:
    probe = _WarmupProbe(tmp_path)

    phrases = TTSPipelineCacheQueueMixin._current_time_cache_phrases(probe)

    assert len(phrases) >= 2
    assert len(phrases) == len(set(phrases))
    for phrase in phrases:
        assert len(phrase) == 5
        assert phrase[2] == " "
        assert phrase[:2].isdigit()
        assert phrase[3:].isdigit()

def test_default_common_cache_includes_natural_help_responses() -> None:
    pipeline = TTSPipeline(enabled=False, preferred_engine="piper")

    assert "I can talk with you, help you remember something, tell you the time, show the desktop, and report runtime status, tests, and benchmarks." in pipeline._common_cache_phrases["en"]
    assert "Mogę z Tobą porozmawiać, pomóc Ci coś zapamiętać, podać czas, pokazać pulpit oraz przedstawić status runtime, testy i benchmarki." in pipeline._common_cache_phrases["pl"]
