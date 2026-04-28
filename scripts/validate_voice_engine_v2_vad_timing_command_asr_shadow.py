from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.validate_voice_engine_v2_command_asr_shadow_bridge import (  # noqa: E402
    validate_command_asr_shadow_bridge_log,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")
EXPECTED_HOOK = "capture_window_pre_transcription"


def validate_vad_timing_command_asr_shadow_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_candidate_attached: bool = False,
    require_disabled_only: bool = False,
    require_capture_window_hook: bool = True,
) -> dict[str, Any]:
    base_result = validate_command_asr_shadow_bridge_log(
        log_path=log_path,
        require_records=require_records,
        require_candidate_attached=require_candidate_attached,
        require_disabled_only=require_disabled_only,
    )

    if not log_path.exists():
        return {
            **base_result,
            "validator": "vad_timing_command_asr_shadow",
            "expected_log_path": str(DEFAULT_LOG_PATH),
        }

    issues = list(base_result.get("issues", []))

    bridge_records = 0
    capture_window_hook_records = 0
    non_capture_window_hook_records = 0
    legacy_runtime_primary_records = 0
    non_legacy_runtime_primary_records = 0

    top_level_unsafe_action_records = 0
    top_level_unsafe_full_stt_records = 0
    top_level_unsafe_takeover_records = 0

    candidate_source_counts: Counter[str] = Counter()
    candidate_publish_stage_counts: Counter[str] = Counter()
    hook_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    capture_mode_counts: Counter[str] = Counter()

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        metadata = _mapping(record.get("metadata"))
        bridge = _mapping(metadata.get("command_asr_shadow_bridge"))
        if not bridge:
            continue

        bridge_records += 1

        hook = str(record.get("hook") or "")
        phase = str(record.get("phase") or "")
        capture_mode = str(record.get("capture_mode") or "")

        if hook:
            hook_counts[hook] += 1
        if phase:
            phase_counts[phase] += 1
        if capture_mode:
            capture_mode_counts[capture_mode] += 1

        if hook == EXPECTED_HOOK:
            capture_window_hook_records += 1
        else:
            non_capture_window_hook_records += 1
            if require_capture_window_hook:
                issues.append(
                    f"line_{line_number}:unexpected_hook:{hook or '<missing>'}"
                )

        if bool(record.get("legacy_runtime_primary", False)):
            legacy_runtime_primary_records += 1
        else:
            non_legacy_runtime_primary_records += 1
            issues.append(f"line_{line_number}:legacy_runtime_primary_not_true")

        if bool(record.get("action_executed", False)):
            top_level_unsafe_action_records += 1
            issues.append(f"line_{line_number}:top_level_action_executed")
        if bool(record.get("full_stt_prevented", False)):
            top_level_unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:top_level_full_stt_prevented")
        if bool(record.get("runtime_takeover", False)):
            top_level_unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:top_level_runtime_takeover")

        candidate = _mapping(metadata.get("command_asr_candidate"))
        if candidate:
            source = str(candidate.get("source") or "")
            publish_stage = str(candidate.get("publish_stage") or "")
            if source:
                candidate_source_counts[source] += 1
            if publish_stage:
                candidate_publish_stage_counts[publish_stage] += 1

    accepted = not issues

    return {
        **base_result,
        "validator": "vad_timing_command_asr_shadow",
        "expected_log_path": str(DEFAULT_LOG_PATH),
        "accepted": accepted,
        "bridge_records": bridge_records,
        "capture_window_hook_records": capture_window_hook_records,
        "non_capture_window_hook_records": non_capture_window_hook_records,
        "legacy_runtime_primary_records": legacy_runtime_primary_records,
        "non_legacy_runtime_primary_records": non_legacy_runtime_primary_records,
        "top_level_unsafe_action_records": top_level_unsafe_action_records,
        "top_level_unsafe_full_stt_records": top_level_unsafe_full_stt_records,
        "top_level_unsafe_takeover_records": top_level_unsafe_takeover_records,
        "hook_counts": dict(hook_counts),
        "phase_counts": dict(phase_counts),
        "capture_mode_counts": dict(capture_mode_counts),
        "candidate_source_counts": dict(candidate_source_counts),
        "candidate_publish_stage_counts": dict(candidate_publish_stage_counts),
        "required_capture_window_hook": require_capture_window_hook,
        "issues": issues,
    }


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Voice Engine v2 command ASR shadow bridge records embedded "
            "inside VAD timing bridge telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-records", action="store_true")
    parser.add_argument("--require-candidate-attached", action="store_true")
    parser.add_argument("--require-disabled-only", action="store_true")
    parser.add_argument(
        "--allow-non-capture-window-hook",
        action="store_true",
        help=(
            "Allow bridge records outside capture_window_pre_transcription. "
            "This should not be used for Stage 24U/24V validation."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_vad_timing_command_asr_shadow_log(
        log_path=args.log_path,
        require_records=args.require_records,
        require_candidate_attached=args.require_candidate_attached,
        require_disabled_only=args.require_disabled_only,
        require_capture_window_hook=not args.allow_non_capture_window_hook,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())