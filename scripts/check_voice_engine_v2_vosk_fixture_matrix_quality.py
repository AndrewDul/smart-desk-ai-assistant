from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_fixture_quality_gate import (  # noqa: E402
    DEFAULT_MATRIX_SUMMARY_PATH,
    SUPPORTED_LANGUAGES,
    check_vosk_fixture_matrix_quality,
)


DEFAULT_OUTPUT_PATH = Path("var/data/stage24ah_vosk_fixture_quality_gate.json")


def run_vosk_fixture_quality_gate(
    *,
    summary_path: Path = DEFAULT_MATRIX_SUMMARY_PATH,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
    min_total_items: int = 6,
    min_accepted_items: int = 6,
    max_failed_items: int = 0,
    min_total_reports: int = 6,
    min_matched_reports: int = 6,
    min_language_match_records: int = 6,
    max_language_mismatch_records: int = 0,
    max_unsafe_flag_records: int = 0,
    max_elapsed_ms: float | None = None,
    require_languages: tuple[str, ...] = ("en", "pl"),
) -> dict[str, object]:
    result = check_vosk_fixture_matrix_quality(
        summary_path=summary_path,
        min_total_items=min_total_items,
        min_accepted_items=min_accepted_items,
        max_failed_items=max_failed_items,
        min_total_reports=min_total_reports,
        min_matched_reports=min_matched_reports,
        min_language_match_records=min_language_match_records,
        max_language_mismatch_records=max_language_mismatch_records,
        max_unsafe_flag_records=max_unsafe_flag_records,
        max_elapsed_ms=max_elapsed_ms,
        require_languages=require_languages,
    )

    payload: dict[str, object] = {
        **result,
        "action": "check_vosk_fixture_matrix_quality",
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
            "Check the offline Voice Engine v2 Vosk fixture matrix quality gate. "
            "This only reads a local matrix summary JSON and never starts live "
            "runtime, microphone streaming, or command execution."
        )
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_MATRIX_SUMMARY_PATH,
        help="Path to the Stage 24AG matrix summary JSON.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path where the quality gate result JSON should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a quality gate result JSON file.",
    )
    parser.add_argument(
        "--min-total-items",
        type=int,
        default=6,
        help="Minimum required matrix items.",
    )
    parser.add_argument(
        "--min-accepted-items",
        type=int,
        default=6,
        help="Minimum required accepted matrix items.",
    )
    parser.add_argument(
        "--max-failed-items",
        type=int,
        default=0,
        help="Maximum allowed failed matrix items.",
    )
    parser.add_argument(
        "--min-total-reports",
        type=int,
        default=6,
        help="Minimum required aggregate reports.",
    )
    parser.add_argument(
        "--min-matched-reports",
        type=int,
        default=6,
        help="Minimum required matched reports.",
    )
    parser.add_argument(
        "--min-language-match-records",
        type=int,
        default=6,
        help="Minimum required language-matched records.",
    )
    parser.add_argument(
        "--max-language-mismatch-records",
        type=int,
        default=0,
        help="Maximum allowed language mismatches.",
    )
    parser.add_argument(
        "--max-unsafe-flag-records",
        type=int,
        default=0,
        help="Maximum allowed unsafe flag records.",
    )
    parser.add_argument(
        "--max-elapsed-ms",
        type=float,
        default=None,
        help="Optional maximum allowed aggregate max elapsed_ms.",
    )
    parser.add_argument(
        "--require-language",
        action="append",
        choices=SUPPORTED_LANGUAGES,
        default=[],
        help="Require at least one accepted report for this command language.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    require_languages = tuple(args.require_language or ("en", "pl"))

    result = run_vosk_fixture_quality_gate(
        summary_path=args.summary_path,
        output_path=None if args.no_output else args.output_path,
        min_total_items=args.min_total_items,
        min_accepted_items=args.min_accepted_items,
        max_failed_items=args.max_failed_items,
        min_total_reports=args.min_total_reports,
        min_matched_reports=args.min_matched_reports,
        min_language_match_records=args.min_language_match_records,
        max_language_mismatch_records=args.max_language_mismatch_records,
        max_unsafe_flag_records=args.max_unsafe_flag_records,
        max_elapsed_ms=args.max_elapsed_ms,
        require_languages=require_languages,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())