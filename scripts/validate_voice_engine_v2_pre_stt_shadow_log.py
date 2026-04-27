#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_pre_stt_shadow.jsonl")

DEFAULT_ALLOWED_REASONS = (
    "audio_bus_unavailable_observe_only",
    "audio_bus_available_observe_only",
)

REQUIRED_FIELDS = (
    "turn_id",
    "phase",
    "capture_mode",
    "input_owner",
    "observed",
    "reason",
    "legacy_runtime_primary",
    "action_executed",
    "full_stt_prevented",
)


@dataclass(frozen=True, slots=True)
class PreSttShadowValidationIssue:
    """One validation issue found in a pre-STT shadow telemetry record."""

    line_number: int
    code: str
    message: str
    record: dict[str, Any] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "code": self.code,
            "message": self.message,
            "record": self.record or {},
        }


@dataclass(frozen=True, slots=True)
class PreSttShadowLogValidationResult:
    """Validation summary for Voice Engine v2 pre-STT shadow telemetry."""

    accepted: bool
    log_path: str
    total_lines: int
    valid_json_records: int
    observed_records: int
    not_observed_records: int
    reasons: dict[str, int]
    phases: dict[str, int]
    capture_modes: dict[str, int]
    required_observed: bool
    issues: tuple[PreSttShadowValidationIssue, ...] = field(default_factory=tuple)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "log_path": self.log_path,
            "total_lines": self.total_lines,
            "valid_json_records": self.valid_json_records,
            "observed_records": self.observed_records,
            "not_observed_records": self.not_observed_records,
            "reasons": dict(self.reasons),
            "phases": dict(self.phases),
            "capture_modes": dict(self.capture_modes),
            "required_observed": self.required_observed,
            "issues": [issue.to_json_dict() for issue in self.issues],
        }


def validate_pre_stt_shadow_log(
    path: Path,
    *,
    allowed_reasons: tuple[str, ...] = DEFAULT_ALLOWED_REASONS,
    require_records: bool = True,
    require_observed: bool = False,
) -> PreSttShadowLogValidationResult:
    issues: list[PreSttShadowValidationIssue] = []
    reasons: Counter[str] = Counter()
    phases: Counter[str] = Counter()
    capture_modes: Counter[str] = Counter()

    total_lines = 0
    valid_json_records = 0
    observed_records = 0
    not_observed_records = 0

    if not path.exists():
        issues.append(
            PreSttShadowValidationIssue(
                line_number=0,
                code="missing_log",
                message=f"Pre-STT shadow log does not exist: {path}",
            )
        )
        return _build_result(
            path=path,
            total_lines=0,
            valid_json_records=0,
            observed_records=0,
            not_observed_records=0,
            reasons=reasons,
            phases=phases,
            capture_modes=capture_modes,
            require_observed=require_observed,
            issues=issues,
            require_records=require_records,
        )

    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            total_lines += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append(
                    PreSttShadowValidationIssue(
                        line_number=line_number,
                        code="invalid_json",
                        message=str(error),
                    )
                )
                continue

            if not isinstance(record, dict):
                issues.append(
                    PreSttShadowValidationIssue(
                        line_number=line_number,
                        code="record_not_object",
                        message="Telemetry record must be a JSON object.",
                        record={"raw": record},
                    )
                )
                continue

            valid_json_records += 1

            _validate_record_shape(
                record=record,
                line_number=line_number,
                issues=issues,
            )

            observed = bool(record.get("observed", False))
            reason = str(record.get("reason", "") or "")
            phase = str(record.get("phase", "") or "")
            capture_mode = str(record.get("capture_mode", "") or "")

            reasons[reason] += 1
            phases[phase] += 1
            capture_modes[capture_mode] += 1

            if observed:
                observed_records += 1
            else:
                not_observed_records += 1

            _validate_safety_fields(
                record=record,
                line_number=line_number,
                allowed_reasons=allowed_reasons,
                issues=issues,
            )

    return _build_result(
        path=path,
        total_lines=total_lines,
        valid_json_records=valid_json_records,
        observed_records=observed_records,
        not_observed_records=not_observed_records,
        reasons=reasons,
        phases=phases,
        capture_modes=capture_modes,
        require_observed=require_observed,
        issues=issues,
        require_records=require_records,
    )


def _validate_record_shape(
    *,
    record: dict[str, Any],
    line_number: int,
    issues: list[PreSttShadowValidationIssue],
) -> None:
    for field_name in REQUIRED_FIELDS:
        if field_name not in record:
            issues.append(
                PreSttShadowValidationIssue(
                    line_number=line_number,
                    code="missing_required_field",
                    message=f"Missing required field: {field_name}",
                    record=record,
                )
            )

    for bool_field in (
        "observed",
        "legacy_runtime_primary",
        "action_executed",
        "full_stt_prevented",
    ):
        if bool_field in record and not isinstance(record[bool_field], bool):
            issues.append(
                PreSttShadowValidationIssue(
                    line_number=line_number,
                    code=f"{bool_field}_not_bool",
                    message=f"Field {bool_field} must be a boolean.",
                    record=record,
                )
            )


def _validate_safety_fields(
    *,
    record: dict[str, Any],
    line_number: int,
    allowed_reasons: tuple[str, ...],
    issues: list[PreSttShadowValidationIssue],
) -> None:
    reason = str(record.get("reason", "") or "")
    legacy_runtime_primary = bool(record.get("legacy_runtime_primary", False))
    action_executed = bool(record.get("action_executed", False))
    full_stt_prevented = bool(record.get("full_stt_prevented", False))

    if reason not in allowed_reasons:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=line_number,
                code="reason_not_allowed",
                message=f"Reason is not allowed for Stage 21C hardware validation: {reason}",
                record=record,
            )
        )

    if not legacy_runtime_primary:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=line_number,
                code="legacy_runtime_not_primary",
                message="Pre-STT shadow must keep legacy_runtime_primary=true.",
                record=record,
            )
        )

    if action_executed:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=line_number,
                code="action_executed",
                message="Pre-STT shadow must never execute actions.",
                record=record,
            )
        )

    if full_stt_prevented:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=line_number,
                code="full_stt_prevented",
                message="Pre-STT shadow must never prevent legacy full STT.",
                record=record,
            )
        )


def _build_result(
    *,
    path: Path,
    total_lines: int,
    valid_json_records: int,
    observed_records: int,
    not_observed_records: int,
    reasons: Counter[str],
    phases: Counter[str],
    capture_modes: Counter[str],
    require_observed: bool,
    issues: list[PreSttShadowValidationIssue],
    require_records: bool,
) -> PreSttShadowLogValidationResult:
    if require_records and valid_json_records == 0:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=0,
                code="no_records",
                message="Pre-STT shadow log contains no valid telemetry records.",
            )
        )

    if require_observed and observed_records == 0:
        issues.append(
            PreSttShadowValidationIssue(
                line_number=0,
                code="no_observed_records",
                message="Pre-STT shadow log contains no observed records.",
            )
        )

    return PreSttShadowLogValidationResult(
        accepted=not issues,
        log_path=str(path),
        total_lines=total_lines,
        valid_json_records=valid_json_records,
        observed_records=observed_records,
        not_observed_records=not_observed_records,
        reasons=dict(sorted(reasons.items())),
        phases=dict(sorted(phases.items())),
        capture_modes=dict(sorted(capture_modes.items())),
        required_observed=require_observed,
        issues=tuple(issues),
    )


def parse_string_list(raw_values: list[str] | None) -> tuple[str, ...]:
    if not raw_values:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_value in raw_values:
        for item in raw_value.split(","):
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)

    return tuple(normalized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Voice Engine v2 pre-STT shadow JSONL telemetry."
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to var/data/voice_engine_v2_pre_stt_shadow.jsonl.",
    )
    parser.add_argument(
        "--require-observed",
        action="store_true",
        help="Require at least one observed=true record.",
    )
    parser.add_argument(
        "--allow-reason",
        action="append",
        default=[],
        help=(
            "Override allowed reasons. Can be used multiple times or with "
            "comma-separated values."
        ),
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail when the log has no records.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    allowed_reasons = parse_string_list(args.allow_reason)
    if not allowed_reasons:
        allowed_reasons = DEFAULT_ALLOWED_REASONS

    result = validate_pre_stt_shadow_log(
        args.log_path,
        allowed_reasons=allowed_reasons,
        require_records=not args.allow_empty,
        require_observed=bool(args.require_observed),
    )

    print(json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())