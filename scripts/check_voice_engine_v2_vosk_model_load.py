#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_text = str(PROJECT_ROOT)
if project_root_text not in sys.path:
    sys.path.insert(0, project_root_text)

from modules.devices.audio.command_asr.command_grammar import (  # noqa: E402
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage  # noqa: E402
from modules.devices.audio.command_asr.vosk_command_recognizer import (  # noqa: E402
    DEFAULT_VOSK_MODEL_PATH,
    DEFAULT_VOSK_SAMPLE_RATE,
    LocalVoskPcmTranscriptProvider,
    _resolve_vosk_model_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether the local Vosk command model can be loaded."
    )
    parser.add_argument(
        "--model-path",
        default=DEFAULT_VOSK_MODEL_PATH,
        help="Vosk model directory or parent directory.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_VOSK_SAMPLE_RATE,
    )
    parser.add_argument(
        "--grammar-language",
        choices=("auto", "en", "pl", "all"),
        default="auto",
        help="Limit Vosk grammar phrases to a language.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = _resolve_vosk_model_path(Path(args.model_path))
    grammar = build_default_command_grammar()
    grammar_language = _select_grammar_language(
        mode=args.grammar_language,
        model_path=model_path,
    )

    grammar_phrases = grammar.to_vosk_vocabulary(language=grammar_language)

    provider = LocalVoskPcmTranscriptProvider(
        model_path=model_path,
        sample_rate=args.sample_rate,
        grammar_phrases=grammar_phrases,
    )

    try:
        transcript = provider(b"\x00\x00" * 1600)
    except Exception as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "model_path": str(model_path),
                    "sample_rate": args.sample_rate,
                    "grammar_language": (
                        grammar_language.value if grammar_language else "all"
                    ),
                    "grammar_phrase_count": len(grammar_phrases),
                    "error": f"{type(error).__name__}: {error}",
                    "microphone_stream_started": False,
                    "runtime_takeover": False,
                    "command_execution_enabled": False,
                    "raw_pcm_logged": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "accepted": True,
                "model_path": str(model_path),
                "sample_rate": args.sample_rate,
                "grammar_language": grammar_language.value if grammar_language else "all",
                "grammar_phrase_count": len(grammar_phrases),
                "silent_pcm_transcript": transcript or "",
                "microphone_stream_started": False,
                "runtime_takeover": False,
                "command_execution_enabled": False,
                "raw_pcm_logged": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _select_grammar_language(
    *,
    mode: str,
    model_path: Path,
) -> CommandLanguage | None:
    if mode == "en":
        return CommandLanguage.ENGLISH
    if mode == "pl":
        return CommandLanguage.POLISH
    if mode == "all":
        return None

    model_name = model_path.name.lower()
    if "-pl-" in model_name or model_name.endswith("-pl") or "polish" in model_name:
        return CommandLanguage.POLISH
    if "-en-" in model_name or model_name.endswith("-en") or "english" in model_name:
        return CommandLanguage.ENGLISH

    return None


if __name__ == "__main__":
    raise SystemExit(main())
