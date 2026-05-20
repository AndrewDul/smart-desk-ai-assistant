"""Play the deterministic time reply through the configured NeXa TTS backend."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.devices.audio.output.tts_pipeline import TTSPipeline


REPO_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"


def _load_voice_output_config() -> dict[str, object]:
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    voice_output = payload.get("voice_output", {})
    return dict(voice_output or {}) if isinstance(voice_output, dict) else {}


def build_probe_report(*, play_audio: bool = True) -> dict[str, object]:
    config = _load_voice_output_config()
    now = datetime.now(ZoneInfo("Europe/London"))
    generated_time_text = now.strftime("%H %M")

    tts = TTSPipeline(
        enabled=bool(config.get("enabled", True)),
        preferred_engine=str(config.get("engine", "piper")),
        default_language=str(config.get("default_language", "en")),
        speed=int(config.get("speed", 155)),
        pitch=int(config.get("pitch", 58)),
        voices=config.get("voices"),
        piper_models=config.get("piper_models"),
        process_poll_seconds=float(config.get("process_poll_seconds", 0.02) or 0.02),
        synthesis_poll_seconds=float(config.get("synthesis_poll_seconds", 0.005) or 0.005),
        playback_poll_seconds=float(config.get("playback_poll_seconds", 0.005) or 0.005),
        preferred_playback_backend=str(config.get("preferred_playback_backend", "") or ""),
        direct_sounddevice_playback_enabled=bool(
            config.get("direct_sounddevice_playback_enabled", False)
        ),
        allow_espeak_fallback=bool(config.get("allow_espeak_fallback", False)),
        console_echo_enabled=bool(config.get("console_echo_enabled", False)),
        spoken_text_log_enabled=bool(config.get("spoken_text_log_enabled", False)),
        hot_path_success_log_enabled=bool(config.get("hot_path_success_log_enabled", False)),
        runtime_wav_directory=str(config.get("runtime_wav_directory", "") or ""),
    )

    delivered = False
    last_error = ""
    if play_audio:
        try:
            delivered = bool(tts.speak(generated_time_text, language="en"))
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"

    speak_report = tts.latest_speak_report()
    if not last_error:
        last_error = str(speak_report.get("playback_stderr", "") or "")
    if not last_error and speak_report.get("success") is False:
        last_error = "tts playback did not report success"

    return {
        "probe": "time_tts_playback_probe",
        "generated_time_text": generated_time_text,
        "play_audio": bool(play_audio),
        "selected_playback_backend": speak_report.get("playback_backend")
        or speak_report.get("engine")
        or "",
        "playback_command": speak_report.get("playback_command", ""),
        "audio_file": speak_report.get("audio_file", ""),
        "audio_file_exists": bool(speak_report.get("audio_file_exists", False)),
        "audio_file_size_bytes": int(speak_report.get("audio_file_size_bytes", 0) or 0),
        "playback_process_started": bool(speak_report.get("playback_process_started", False)),
        "playback_exit_code": speak_report.get("playback_exit_code"),
        "playback_stderr": speak_report.get("playback_stderr", ""),
        "delivered": bool(delivered),
        "last_error": last_error,
    }


def main() -> int:
    print(json.dumps(build_probe_report(play_audio=True), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
