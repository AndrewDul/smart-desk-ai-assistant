from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_fixture_recognition_probe import (  # noqa: E402
    probe_vosk_fixture_recognition,
    validate_vosk_fixture_recognition_result,
)


DEFAULT_OUTPUT_PATH = Path("var/data/voice_engine_v2_vosk_fixture_recognition_probe.json")


def run_vosk_fixture_recognition_probe(
    *,
    model_path: Path,
    wav_path: Path,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
    require_command_match: bool = False,
) -> dict[str, object]:
    result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
    )
    validation = validate_vosk_fixture_recognition_result(
        result=result,
        require_command_match=require_command_match,
    )

    payload = {
        **validation,
        "action": "probe_vosk_fixture_recognition",
        "output_path": str(output_path) if output_path is not None else "",
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe Vosk command recognition on an offline WAV fixture. "
            "This does not start live runtime, microphone streaming, or command execution."
        )
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        required=True,
        help="Path to a local Vosk model directory.",
    )
    parser.add_argument(
        "--wav-path",
        type=Path,
        required=True,
        help="Path to a mono 16 kHz PCM16 WAV fixture.",
    )
    parser.add_argument(
        "--require-command-match",
        action="store_true",
        help="Fail if the recognized text does not match command grammar.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path where the JSON report should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a JSON report file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_vosk_fixture_recognition_probe(
        model_path=args.model_path,
        wav_path=args.wav_path,
        output_path=None if args.no_output else args.output_path,
        require_command_match=args.require_command_match,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())