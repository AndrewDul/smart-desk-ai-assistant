from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_model_probe import (  # noqa: E402
    DEFAULT_VOSK_MODEL_PATHS,
    probe_vosk_models,
)


DEFAULT_OUTPUT_PATH = Path("var/data/voice_engine_v2_vosk_model_probe.json")


def run_vosk_model_probe(
    *,
    model_paths: tuple[Path, ...] | None = None,
    load_model: bool = False,
    require_model_present: bool = False,
    require_loadable: bool = False,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
) -> dict[str, object]:
    result = probe_vosk_models(
        model_paths=model_paths,
        load_model=load_model,
        require_model_present=require_model_present,
        require_loadable=require_loadable,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        **result,
        "action": "probe_vosk_models",
        "output_path": str(output_path) if output_path is not None else "",
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "active_command_recognition_enabled": False,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe local Vosk model directories for Voice Engine v2 without "
            "starting runtime command recognition."
        )
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        action="append",
        default=None,
        help=(
            "Local Vosk model path. Can be passed multiple times. "
            "If omitted, safe default candidate paths are checked."
        ),
    )
    parser.add_argument(
        "--load-model",
        action="store_true",
        help=(
            "Attempt to import vosk and instantiate Model(path). "
            "This does not start microphone capture or command recognition."
        ),
    )
    parser.add_argument(
        "--require-model-present",
        action="store_true",
        help="Fail if no local model directory is found.",
    )
    parser.add_argument(
        "--require-loadable",
        action="store_true",
        help="Fail if no model loads successfully. Requires --load-model.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path where the probe JSON report should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a JSON report file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    model_paths = (
        tuple(args.model_path)
        if args.model_path is not None
        else DEFAULT_VOSK_MODEL_PATHS
    )

    result = run_vosk_model_probe(
        model_paths=model_paths,
        load_model=args.load_model,
        require_model_present=args.require_model_present,
        require_loadable=args.require_loadable,
        output_path=None if args.no_output else args.output_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())