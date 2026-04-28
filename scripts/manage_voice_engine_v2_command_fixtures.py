from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.command_fixture_inventory import (  # noqa: E402
    DEFAULT_FIXTURE_ROOT,
    import_command_fixture,
    inventory_command_fixtures,
    validate_command_fixture_inventory,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manage local Voice Engine v2 command WAV fixtures. "
            "Fixtures are local runtime assets and must not be committed to git."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--source-wav", type=Path, required=True)
    import_parser.add_argument("--fixture-id", required=True)
    import_parser.add_argument("--language", choices=("en", "pl"), required=True)
    import_parser.add_argument("--phrase", required=True)
    import_parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    import_parser.add_argument("--overwrite", action="store_true")
    import_parser.add_argument("--max-duration-ms", type=float, default=5_000.0)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
    )

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
    )
    validate_parser.add_argument("--require-records", action="store_true")
    validate_parser.add_argument(
        "--require-language",
        action="append",
        choices=("en", "pl"),
        default=[],
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.action == "import":
        result = import_command_fixture(
            source_wav_path=args.source_wav,
            fixture_id=args.fixture_id,
            language=args.language,
            phrase=args.phrase,
            fixture_root=args.fixture_root,
            overwrite=args.overwrite,
            max_duration_ms=args.max_duration_ms,
        )
    elif args.action == "inventory":
        result = inventory_command_fixtures(fixture_root=args.fixture_root)
    elif args.action == "validate":
        result = validate_command_fixture_inventory(
            fixture_root=args.fixture_root,
            require_records=args.require_records,
            require_languages=tuple(args.require_language or ()),
        )
    else:
        raise ValueError(f"Unsupported action: {args.action}")

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())