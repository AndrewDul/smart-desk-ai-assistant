"""
In-process persistent Piper voice daemon for NeXa.

Design:
- keeps one PiperVoice instance loaded per language for the full lifetime
  of the TTS pipeline
- bypasses subprocess + Python interpreter startup + ONNX model reload
  on every utterance
- produces WAV files in the runtime wav directory (tmpfs on /dev/shm)
  so downstream playback via sounddevice starts without disk I/O
- exposes a safe .synthesize() API that falls through (returns False)
  whenever the daemon is unavailable, so the caller can fall back to
  the existing subprocess-based synthesis path without breaking anything
"""
from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from typing import Any

from modules.system.utils import append_log


class PiperDaemon:
    """
    Holds one PiperVoice per language and reuses it across utterances.

    Thread safety:
    - each PiperVoice has its own lock; synthesis of different languages
      can run in parallel, same-language requests are serialized
    - load() is idempotent and safe to call multiple times
    """

    def __init__(self, *, piper_models: dict[str, dict[str, Any]], base_dir: Path) -> None:
        self._piper_models = dict(piper_models or {})
        self._base_dir = Path(base_dir)
        self._voices: dict[str, Any] = {}
        self._voice_locks: dict[str, threading.Lock] = {}
        self._load_lock = threading.Lock()
        self._import_checked = False
        self._piper_voice_cls: Any = None
        self._load_errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return self._ensure_piper_voice_cls() is not None

    def preload_all(self) -> None:
        """Preload every configured language. Safe to call on boot."""
        if not self.is_enabled():
            return
        for lang in list(self._piper_models.keys()):
            self._ensure_voice_loaded(lang)

    def is_language_ready(self, lang: str) -> bool:
        normalized = str(lang or "").strip().lower()
        if not normalized:
            return False
        return self._ensure_voice_loaded(normalized) is not None

    def synthesize(self, *, text: str, lang: str, wav_path: Path) -> bool:
        """
        Synthesize text into wav_path using the in-process Piper voice.

        Returns True on success, False to let the caller fall back to the
        subprocess synthesis path.
        """
        voice = self._ensure_voice_loaded(lang)
        if voice is None:
            return False

        clean_text = str(text or "").strip()
        if not clean_text:
            return False

        lock = self._voice_locks.get(lang)
        if lock is None:
            # Defensive: should not happen because _ensure_voice_loaded
            # initializes the lock, but we still want to stay safe.
            lock = threading.Lock()
            self._voice_locks[lang] = lock

        started_at = time.monotonic()
        try:
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            with lock:
                with wave.open(str(wav_path), "wb") as wav_file:
                    # ALWAYS pre-configure the wave header. Piper 1.3+
                    # synthesize_wav() usually sets these, but on short/
                    # edge-case texts it can skip setup and raise
                    # "# channels not specified". Pre-setting is harmless
                    # when synthesize_wav() overwrites them.
                    sample_rate = None
                    cfg = getattr(voice, "config", None)
                    if cfg is not None:
                        sample_rate = getattr(cfg, "sample_rate", None)
                    if sample_rate is None:
                        sample_rate = getattr(voice, "sample_rate", 22050)
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(int(sample_rate))

                    if hasattr(voice, "synthesize_wav"):
                        voice.synthesize_wav(clean_text, wav_file)
                    else:
                        voice.synthesize(clean_text, wav_file)
        except Exception as error:
            append_log(
                f"Piper daemon synthesis failed: lang={lang}, error={error}"
            )
            # Drop a half-written file so downstream playback does not pick it up.
            if wav_path.exists():
                try:
                    wav_path.unlink()
                except OSError:
                    pass
            return False

        if not wav_path.exists() or wav_path.stat().st_size <= 44:
            append_log(
                f"Piper daemon synthesis produced empty wav: lang={lang}, "
                f"path={wav_path}"
            )
            return False

        elapsed_ms = (time.monotonic() - started_at) * 1000.0
        append_log(
            "Piper daemon synthesis finished: "
            f"lang={lang}, chars={len(clean_text)}, "
            f"elapsed_ms={elapsed_ms:.1f}"
        )
        return True

    def shutdown(self) -> None:
        with self._load_lock:
            self._voices.clear()
            self._voice_locks.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_piper_voice_cls(self) -> Any:
        if self._import_checked:
            return self._piper_voice_cls

        with self._load_lock:
            if self._import_checked:
                return self._piper_voice_cls

            try:
                from piper import PiperVoice  # type: ignore

                self._piper_voice_cls = PiperVoice
                append_log("Piper daemon import OK: in-process PiperVoice available.")
            except Exception as error:
                self._piper_voice_cls = None
                append_log(
                    "Piper daemon disabled: in-process PiperVoice import failed "
                    f"({error}). Falling back to subprocess synthesis."
                )
            finally:
                self._import_checked = True

        return self._piper_voice_cls

    def _ensure_voice_loaded(self, lang: str) -> Any:
        voice_cls = self._ensure_piper_voice_cls()
        if voice_cls is None:
            return None

        normalized = str(lang or "").strip().lower()
        if not normalized:
            return None

        cached = self._voices.get(normalized)
        if cached is not None:
            return cached

        model_info = self._piper_models.get(normalized)
        if not model_info:
            return None

        model_path = self._resolve_model_path(model_info.get("model"))
        config_path = self._resolve_model_path(model_info.get("config"))
        if model_path is None or config_path is None:
            self._load_errors[normalized] = "missing model or config path"
            return None
        if not model_path.exists() or not config_path.exists():
            self._load_errors[normalized] = (
                f"model or config file not found on disk: "
                f"model={model_path}, config={config_path}"
            )
            return None

        with self._load_lock:
            cached = self._voices.get(normalized)
            if cached is not None:
                return cached

            started_at = time.monotonic()
            try:
                voice = voice_cls.load(
                    str(model_path),
                    config_path=str(config_path),
                    use_cuda=False,
                )
            except TypeError:
                # Older piper versions do not accept use_cuda.
                try:
                    voice = voice_cls.load(str(model_path), str(config_path))
                except Exception as error:
                    append_log(
                        f"Piper daemon voice load failed: lang={normalized}, "
                        f"error={error}"
                    )
                    self._load_errors[normalized] = str(error)
                    return None
            except Exception as error:
                append_log(
                    f"Piper daemon voice load failed: lang={normalized}, "
                    f"error={error}"
                )
                self._load_errors[normalized] = str(error)
                return None

            self._voices[normalized] = voice
            self._voice_locks[normalized] = threading.Lock()

            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            append_log(
                "Piper daemon voice ready: "
                f"lang={normalized}, elapsed_ms={elapsed_ms:.1f}, "
                f"model={model_path.name}"
            )
            return voice

    def _resolve_model_path(self, candidate: Any) -> Path | None:
        if not candidate:
            return None
        raw = Path(str(candidate))
        if raw.is_absolute():
            return raw
        return self._base_dir / raw


__all__ = ["PiperDaemon"]