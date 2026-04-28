from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_fixture_report_summary import (  # noqa: E402
    DEFAULT_REPORT_PATTERN,
    SUPPORTED_LANGUAGES,
    summarize_vosk_fixture_reports,
)


DEFAULT_REPORT_DIR = Path("var/data/stage24ae_vosk_fixture_probes")
DEFAULT_OUTPUT_PATH = Path("var/data/voice_engine_v2_vosk_fixture_report_summary.json")


def run_vosk_fixture_report_summary(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    report_pattern: str = DEFAULT_REPORT_PATTERN,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
    require_reports: bool = False,
    require_languages: tuple[str, ...] = (),
) -> dict[str, object]:
    result = summarize_vosk_fixture_reports(
        report_dir=report_dir,
        report_pattern=report_pattern,
        require_reports=require_reports,
        require_languages=require_languages,
    )

    payload: dict[str, object] = {
        **result,
        "action": "summarize_vosk_fixture_reports",
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
            "Summarize offline Voice Engine v2 Vosk fixture recognition reports. "
            "This does not start live runtime, microphone streaming, or command execution."
        )
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory containing offline Vosk fixture recognition JSON reports.",
    )
    parser.add_argument(
        "--report-pattern",
        default=DEFAULT_REPORT_PATTERN,
        help="Glob pattern used to discover report files inside report-dir.",
    )
    parser.add_argument(
        "--require-reports",
        action="store_true",
        help="Fail if no JSON reports are found.",
    )
    parser.add_argument(
        "--require-language",
        action="append",
        choices=SUPPORTED_LANGUAGES,
        default=[],
        help="Require at least one accepted command report for this language.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path where the aggregate summary JSON should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write an aggregate summary JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_vosk_fixture_report_summary(
        report_dir=args.report_dir,
        report_pattern=args.report_pattern,
        output_path=None if args.no_output else args.output_path,
        require_reports=args.require_reports,
        require_languages=tuple(args.require_language or ()),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())