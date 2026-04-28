from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.vosk_live_shadow_contract import (  # noqa: E402
    VoskLiveShadowContractSettings,
    build_vosk_live_shadow_contract,
    validate_vosk_live_shadow_contract_result,
)


DEFAULT_OUTPUT_PATH = Path("var/data/voice_engine_v2_vosk_live_shadow_contract.json")


def run_vosk_live_shadow_contract_validation(
    *,
    enabled_contract: bool = False,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
) -> dict[str, object]:
    contract = build_vosk_live_shadow_contract(
        settings=VoskLiveShadowContractSettings(enabled=enabled_contract),
    )
    validation = validate_vosk_live_shadow_contract_result(contract)

    payload: dict[str, object] = {
        **validation,
        "action": "validate_vosk_live_shadow_contract",
        "output_path": str(output_path) if output_path is not None else "",
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
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
            "Validate the Voice Engine v2 Vosk live shadow contract. "
            "This is contract-only and does not start runtime, microphone "
            "capture, Vosk recognition, command execution, or FasterWhisper bypass."
        )
    )
    parser.add_argument(
        "--enabled-contract",
        action="store_true",
        help=(
            "Validate the enabled-but-not-attached contract shape. "
            "This still does not start recognition."
        ),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path where the validation JSON should be written.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write validation JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_vosk_live_shadow_contract_validation(
        enabled_contract=args.enabled_contract,
        output_path=None if args.no_output else args.output_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())