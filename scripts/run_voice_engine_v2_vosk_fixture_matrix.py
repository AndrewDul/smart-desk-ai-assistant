from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_fixture_matrix_runner import (  # noqa: E402
    DEFAULT_MATRIX_REPORT_DIR,
    DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH,
    VoskFixtureMatrixItem,
    run_vosk_fixture_matrix,
)
from modules.runtime.voice_engine_v2.vosk_fixture_report_summary import (  # noqa: E402
    SUPPORTED_LANGUAGES,
)


def run_voice_engine_v2_vosk_fixture_matrix(
    *,
    report_dir: Path = DEFAULT_MATRIX_REPORT_DIR,
    summary_output_path: Path | None = DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH,
    require_languages: tuple[str, ...] = ("en", "pl"),
    items: tuple[VoskFixtureMatrixItem, ...] | None = None,
) -> dict[str, object]:
    return run_vosk_fixture_matrix(
        report_dir=report_dir,
        summary_output_path=summary_output_path,
        require_languages=require_languages,
        items=items,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline Voice Engine v2 Vosk fixture matrix. "
            "This writes per-fixture reports and an aggregate summary without "
            "starting live runtime, microphone streaming, or command execution."
        )
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_MATRIX_REPORT_DIR,
        help="Directory where per-fixture matrix probe reports should be written.",
    )
    parser.add_argument(
        "--summary-output-path",
        type=Path,
        default=DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH,
        help="Path where the matrix aggregate summary should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write the matrix aggregate summary JSON file.",
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

    result = run_voice_engine_v2_vosk_fixture_matrix(
        report_dir=args.report_dir,
        summary_output_path=None if args.no_output else args.summary_output_path,
        require_languages=require_languages,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())