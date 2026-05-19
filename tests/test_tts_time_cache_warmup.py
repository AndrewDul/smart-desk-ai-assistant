from __future__ import annotations

from modules.devices.audio.output.tts_pipeline import TTSPipeline

import threading
from pathlib import Path

from modules.devices.audio.output.tts_pipeline.cache_queue_mixin import (
    TTSPipelineCacheQueueMixin,
)
from modules.devices.audio.output.tts_pipeline.speech_api_mixin import (
    TTSPipelineSpeechApiMixin,
)
from modules.devices.audio.output.tts_pipeline.control_mixin import (
    TTSPipelineControlMixin,
)
from modules.devices.audio.output.tts_pipeline.wav_playback_mixin import (
    TTSPipelineWavPlaybackMixin,
)
from modules.core.presence import PresenceHeartbeatManager


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


class _PresenceSpeechProbe(TTSPipelineSpeechApiMixin):
    def __init__(self, cache_dir: Path) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self.audio_coordinator = None
        self._presence_playback_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.cache_dir = cache_dir
        self.play_calls = 0
        self.prefetch_calls: list[tuple[str, str]] = []
        self._last_speak_report = {}

    def _normalize_text_for_log(self, text: str) -> str:
        return str(text or "").strip()

    def _resolve_language(self, language: str | None) -> str:
        return str(language or "en").strip() or "en"

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        del lang
        return str(text or "").strip()

    def _piper_model_ready(self, lang: str) -> bool:
        return lang == "en"

    def _cached_wav_path(self, text: str, lang: str) -> Path:
        safe_name = text.replace(" ", "_").replace(".", "dot")
        return self.cache_dir / f"{lang}_{safe_name}.wav"

    def _start_prefetch(self, text: str, lang: str) -> None:
        self.prefetch_calls.append((str(text), str(lang)))

    def _play_wav(self, wav_path: Path, **kwargs):
        del wav_path
        self.last_play_kwargs = dict(kwargs)
        self.play_calls += 1
        return True, 123.0


class _LegacyPiperSpeechProbe(TTSPipelineSpeechApiMixin):
    def __init__(self) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self.audio_coordinator = None
        self._speak_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.piper_calls: list[tuple[str, str, object, object]] = []
        self.espeak_calls: list[tuple[str, str]] = []
        self._last_speak_report = {}
        self._playback_report = {}

    def _normalize_text_for_log(self, text: str) -> str:
        return str(text or "").strip()

    def _resolve_language(self, language: str | None) -> str:
        return str(language or "en").strip() or "en"

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        del lang
        return str(text or "").strip()

    def _normalize_prefetch_request(self, prepare_next):
        return prepare_next

    def clear_stop_request(self) -> None:
        self._stop_requested.clear()

    def _should_echo_spoken_text_to_console(self) -> bool:
        return False

    def _should_log_spoken_text_content(self) -> bool:
        return False

    def _log_spoken_text(self, text: str, lang: str) -> None:
        del text, lang

    def _should_allow_espeak_fallback(self) -> bool:
        return False

    def _log_voice_output_failure(self, lang: str) -> None:
        del lang

    def _should_log_tts_hot_path_success(self) -> bool:
        return False

    def _speak_with_piper(self, text: str, lang: str, *, prepare_next=None, latency_profile=None) -> bool:
        self.piper_calls.append((text, lang, prepare_next, latency_profile))
        self._playback_report = {
            "engine": "piper",
            "success": True,
            "first_audio_started_at_monotonic": 0.0,
            "first_audio_latency_ms": 0.0,
        }
        return True

    def _speak_with_espeak(self, text: str, lang: str) -> bool:
        self.espeak_calls.append((text, lang))
        return False

    def _consume_playback_report(self) -> dict[str, object]:
        report = dict(self._playback_report)
        self._playback_report = {}
        return report


class _PresenceControlProbe(TTSPipelineControlMixin):
    def __init__(self) -> None:
        self._stop_requested = threading.Event()
        self._presence_stop_requested = threading.Event()
        self._process_lock = threading.Lock()
        self._active_presence_processes = []
        self.presence_stream_stopped = False

    def _stop_active_presence_output_stream(self) -> None:
        self.presence_stream_stopped = True

    def _terminate_process(self, process, *, reason: str) -> None:
        del process, reason


class _StopPreservingPlaybackProbe(TTSPipelineWavPlaybackMixin):
    def __init__(self) -> None:
        self._stop_requested = threading.Event()
        self._playback_backends = [("aplay", ["aplay", "-q"])]
        self._playback_timeout_seconds = 1.0
        self._playback_poll_seconds = 0.005
        self._last_good_playback_backend = None
        self._preferred_playback_backend = ""
        self._direct_sounddevice_playback_enabled = False
        self._sounddevice_playback_ready = False
        self.stop_seen_by_runner = False

    def _run_process_interruptibly(self, args, **kwargs) -> bool:
        del args
        callback = kwargs.get("on_process_started")
        if callable(callback):
            callback()
        self.stop_seen_by_runner = self._stop_requested.is_set()
        return not self.stop_seen_by_runner


class _ProcessStartOrderPlaybackProbe(_StopPreservingPlaybackProbe):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def _run_process_interruptibly(self, args, **kwargs) -> bool:
        del args
        self.events.append("process_started")
        callback = kwargs.get("on_process_started")
        if callable(callback):
            callback()
        self.events.append("process_running")
        self.stop_seen_by_runner = self._stop_requested.is_set()
        return not self.stop_seen_by_runner


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


def test_speak_presence_stop_requested_returns_cleanly_without_unbound_error(tmp_path: Path) -> None:
    probe = _PresenceSpeechProbe(tmp_path)
    cached = probe._cached_wav_path("I'm still working on that.", "en")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"RIFFtest")
    probe._stop_requested.set()

    ok, reason = probe.speak_presence("I'm still working on that.", "en")

    assert ok is False
    assert reason == "stop_requested"
    assert probe.play_calls == 0
    assert probe._last_speak_report["first_audio_started_at_monotonic"] == 0.0


def test_speak_retries_legacy_piper_helper_without_first_audio_callback() -> None:
    probe = _LegacyPiperSpeechProbe()
    callback_called = False

    def on_first_audio() -> None:
        nonlocal callback_called
        callback_called = True

    ok = probe.speak(
        "Hello there.",
        "en",
        prepare_next=("Next sentence.", "en"),
        latency_profile="live",
        on_first_audio=on_first_audio,
    )

    assert ok is True
    assert probe.piper_calls == [("Hello there.", "en", ("Next sentence.", "en"), "live")]
    assert probe.espeak_calls == []
    assert callback_called is False


def test_stop_presence_playback_does_not_set_global_stop_request() -> None:
    probe = _PresenceControlProbe()

    probe.stop_presence_playback()

    assert probe._presence_stop_requested.is_set()
    assert not probe._stop_requested.is_set()
    assert probe.presence_stream_stopped is True


def test_real_audio_heartbeat_cancel_does_not_skip_real_playback(tmp_path: Path) -> None:
    probe = _StopPreservingPlaybackProbe()
    wav_path = tmp_path / "reply.wav"
    wav_path.write_bytes(b"RIFFtest")
    presence_control = _PresenceControlProbe()
    heartbeat = PresenceHeartbeatManager(
        voice_output=presence_control,
        first_delay_s=1.0,
    )
    heartbeat._currently_speaking.set()

    def cancel_heartbeat() -> None:
        heartbeat.cancel(reason="real_audio_started")

    ok, _started_at = probe._play_wav(wav_path, on_first_audio=cancel_heartbeat)

    assert ok is True
    assert not probe._stop_requested.is_set()
    assert not probe.stop_seen_by_runner
    assert heartbeat.metrics().cancelled_reason == "real_audio_started"


def test_play_wav_first_audio_callback_does_not_clear_stop_request(tmp_path: Path) -> None:
    probe = _StopPreservingPlaybackProbe()
    wav_path = tmp_path / "reply.wav"
    wav_path.write_bytes(b"RIFFtest")

    def request_stop() -> None:
        probe._stop_requested.set()

    ok, _started_at = probe._play_wav(wav_path, on_first_audio=request_stop)

    assert ok is False
    assert probe._stop_requested.is_set()
    assert probe.stop_seen_by_runner is True


def test_subprocess_first_audio_callback_runs_after_process_start(tmp_path: Path) -> None:
    probe = _ProcessStartOrderPlaybackProbe()
    wav_path = tmp_path / "reply.wav"
    wav_path.write_bytes(b"RIFFtest")

    def on_first_audio() -> None:
        probe.events.append("first_audio")

    ok, started_at = probe._play_wav(wav_path, on_first_audio=on_first_audio)

    assert ok is True
    assert started_at > 0.0
    assert probe.events == ["process_started", "first_audio", "process_running"]


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


def test_default_common_cache_includes_diagnostics_voice_polish_phrases() -> None:
    pipeline = TTSPipeline(enabled=False, preferred_engine="piper")

    for phrase in (
        "One moment, I’m checking that.",
        "Opening diagnostics.",
        "Diagnostics are open.",
        "Diagnostics closed.",
        "I’m NeXa, your local assistant.",
    ):
        assert phrase in pipeline._common_cache_phrases["en"]

    for phrase in (
        "Chwileczkę, sprawdzam to.",
        "Otwieram diagnostykę.",
        "Diagnostyka jest otwarta.",
        "Zamknęłam diagnostykę.",
        "Jestem NeXa, Twoja lokalna asystentka.",
    ):
        assert phrase in pipeline._common_cache_phrases["pl"]


def test_default_common_cache_includes_llm_thinking_ack_prewarm_phrases() -> None:
    pipeline = TTSPipeline(enabled=False, preferred_engine="piper")

    for phrase in (
        "Give me a second, I’m thinking.",
        "Let me think about that for a moment.",
        "Give me a moment, I’m checking the best answer.",
        "Let me explain that clearly.",
        "I’ll break that down simply.",
        "Sure, I’ll help you with that.",
        "Okay, let me think of the best steps.",
        "I’m preparing a useful answer for you.",
    ):
        assert phrase in pipeline._common_cache_phrases["en"], (
            f"LLM prewarm phrase missing from EN cache: {phrase!r}"
        )

    for phrase in (
        "Daj mi chwilę, pomyślę nad tym.",
        "Daj mi sekundę, już nad tym myślę.",
        "Chwileczkę, sprawdzam to.",
        "Daj mi chwilę, wyjaśnię to prosto.",
        "Zaraz wyjaśnię to spokojnie.",
        "Jasne, pomogę Ci z tym.",
        "Daj mi chwilę, ułożę to krok po kroku.",
        "Zaraz podam Ci konkretną odpowiedź.",
    ):
        assert phrase in pipeline._common_cache_phrases["pl"], (
            f"LLM prewarm phrase missing from PL cache: {phrase!r}"
        )
