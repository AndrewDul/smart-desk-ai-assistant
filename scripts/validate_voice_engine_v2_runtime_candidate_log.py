#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_runtime_candidates.jsonl")

DEFAULT_ALLOWED_ACCEPTED_INTENTS = (
    "assistant.identity",
    "system.current_time",
)

EXPECTED_PRIMARY_INTENTS = {
    "assistant.identity": "introduce_self",
    "system.current_time": "ask_time",
}

REQUIRED_FIELDS = (
    "turn_id",
    "transcript",
    "accepted",
    "reason",
    "legacy_runtime_primary",
)


@dataclass(frozen=True, slots=True)
class RuntimeCandidateValidationIssue:
    """One validation issue found in a runtime-candidate telemetry record."""

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
class RuntimeCandidateLogValidationResult:
    """Validation summary for Voice Engine v2 runtime-candidate telemetry."""

    accepted: bool
    log_path: str
    total_lines: int
    valid_json_records: int
    accepted_records: int
    rejected_records: int
    accepted_intents: dict[str, int]
    rejected_reasons: dict[str, int]
    primary_intents: dict[str, int]
    required_intents: tuple[str, ...]
    missing_required_intents: tuple[str, ...]
    issues: tuple[RuntimeCandidateValidationIssue, ...] = field(default_factory=tuple)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "log_path": self.log_path,
            "total_lines": self.total_lines,
            "valid_json_records": self.valid_json_records,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "accepted_intents": dict(self.accepted_intents),
            "rejected_reasons": dict(self.rejected_reasons),
            "primary_intents": dict(self.primary_intents),
            "required_intents": list(self.required_intents),
            "missing_required_intents": list(self.missing_required_intents),
            "issues": [issue.to_json_dict() for issue in self.issues],
        }


def validate_runtime_candidate_log(
    path: Path,
    *,
    allowed_accepted_intents: tuple[str, ...] = DEFAULT_ALLOWED_ACCEPTED_INTENTS,
    required_accepted_intents: tuple[str, ...] = (),
    require_records: bool = True,
) -> RuntimeCandidateLogValidationResult:
    issues: list[RuntimeCandidateValidationIssue] = []
    accepted_intents: Counter[str] = Counter()
    rejected_reasons: Counter[str] = Counter()
    primary_intents: Counter[str] = Counter()

    total_lines = 0
    valid_json_records = 0
    accepted_records = 0
    rejected_records = 0

    if not path.exists():
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=0,
                code="missing_log",
                message=f"Runtime candidate log does not exist: {path}",
            )
        )
        return _build_result(
            path=path,
            total_lines=0,
            valid_json_records=0,
            accepted_records=0,
            rejected_records=0,
            accepted_intents=accepted_intents,
            rejected_reasons=rejected_reasons,
            primary_intents=primary_intents,
            required_accepted_intents=required_accepted_intents,
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
                    RuntimeCandidateValidationIssue(
                        line_number=line_number,
                        code="invalid_json",
                        message=str(error),
                    )
                )
                continue

            if not isinstance(record, dict):
                issues.append(
                    RuntimeCandidateValidationIssue(
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

            accepted = bool(record.get("accepted", False))
            reason = str(record.get("reason", "") or "")
            voice_engine_intent = str(record.get("voice_engine_intent", "") or "")
            primary_intent = str(record.get("primary_intent", "") or "")

            if accepted:
                accepted_records += 1
                accepted_intents[voice_engine_intent] += 1
                primary_intents[primary_intent] += 1
                _validate_accepted_record(
                    record=record,
                    line_number=line_number,
                    allowed_accepted_intents=allowed_accepted_intents,
                    issues=issues,
                )
            else:
                rejected_records += 1
                rejected_reasons[reason] += 1

    return _build_result(
        path=path,
        total_lines=total_lines,
        valid_json_records=valid_json_records,
        accepted_records=accepted_records,
        rejected_records=rejected_records,
        accepted_intents=accepted_intents,
        rejected_reasons=rejected_reasons,
        primary_intents=primary_intents,
        required_accepted_intents=required_accepted_intents,
        issues=issues,
        require_records=require_records,
    )


def _validate_record_shape(
    *,
    record: dict[str, Any],
    line_number: int,
    issues: list[RuntimeCandidateValidationIssue],
) -> None:
    for field_name in REQUIRED_FIELDS:
        if field_name not in record:
            issues.append(
                RuntimeCandidateValidationIssue(
                    line_number=line_number,
                    code="missing_required_field",
                    message=f"Missing required field: {field_name}",
                    record=record,
                )
            )

    if "accepted" in record and not isinstance(record["accepted"], bool):
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="accepted_not_bool",
                message="Field accepted must be a boolean.",
                record=record,
            )
        )

    if "legacy_runtime_primary" in record and not isinstance(
        record["legacy_runtime_primary"],
        bool,
    ):
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="legacy_runtime_primary_not_bool",
                message="Field legacy_runtime_primary must be a boolean.",
                record=record,
            )
        )


def _validate_accepted_record(
    *,
    record: dict[str, Any],
    line_number: int,
    allowed_accepted_intents: tuple[str, ...],
    issues: list[RuntimeCandidateValidationIssue],
) -> None:
    voice_engine_intent = str(record.get("voice_engine_intent", "") or "")
    primary_intent = str(record.get("primary_intent", "") or "")
    route_kind = str(record.get("route_kind", "") or "")
    legacy_runtime_primary = bool(record.get("legacy_runtime_primary", False))
    llm_prevented = bool(record.get("llm_prevented", False))

    if voice_engine_intent not in allowed_accepted_intents:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="accepted_intent_not_allowed",
                message=(
                    f"Accepted intent is not allowed in Stage 20C: "
                    f"{voice_engine_intent}"
                ),
                record=record,
            )
        )

    expected_primary_intent = EXPECTED_PRIMARY_INTENTS.get(voice_engine_intent)
    if expected_primary_intent and primary_intent != expected_primary_intent:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="primary_intent_mismatch",
                message=(
                    f"Accepted intent {voice_engine_intent} must map to "
                    f"{expected_primary_intent}, got {primary_intent}."
                ),
                record=record,
            )
        )

    if not legacy_runtime_primary:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="legacy_runtime_not_primary",
                message="Accepted candidate must keep legacy_runtime_primary=true.",
                record=record,
            )
        )

    if route_kind != "action":
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="accepted_route_not_action",
                message=f"Accepted candidate must use route_kind=action, got {route_kind}.",
                record=record,
            )
        )

    if not llm_prevented:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=line_number,
                code="llm_not_prevented",
                message="Accepted deterministic candidate must have llm_prevented=true.",
                record=record,
            )
        )


def _build_result(
    *,
    path: Path,
    total_lines: int,
    valid_json_records: int,
    accepted_records: int,
    rejected_records: int,
    accepted_intents: Counter[str],
    rejected_reasons: Counter[str],
    primary_intents: Counter[str],
    required_accepted_intents: tuple[str, ...],
    issues: list[RuntimeCandidateValidationIssue],
    require_records: bool,
) -> RuntimeCandidateLogValidationResult:
    if require_records and valid_json_records == 0:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=0,
                code="no_records",
                message="Runtime candidate log contains no valid telemetry records.",
            )
        )

    missing_required_intents = tuple(
        intent
        for intent in required_accepted_intents
        if accepted_intents.get(intent, 0) <= 0
    )

    for intent in missing_required_intents:
        issues.append(
            RuntimeCandidateValidationIssue(
                line_number=0,
                code="missing_required_accepted_intent",
                message=f"Missing required accepted intent: {intent}",
            )
        )

    return RuntimeCandidateLogValidationResult(
        accepted=not issues,
        log_path=str(path),
        total_lines=total_lines,
        valid_json_records=valid_json_records,
        accepted_records=accepted_records,
        rejected_records=rejected_records,
        accepted_intents=dict(sorted(accepted_intents.items())),
        rejected_reasons=dict(sorted(rejected_reasons.items())),
        primary_intents=dict(sorted(primary_intents.items())),
        required_intents=required_accepted_intents,
        missing_required_intents=missing_required_intents,
        issues=tuple(issues),
    )


def parse_intent_list(raw_values: list[str] | None) -> tuple[str, ...]:
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
        description="Validate Voice Engine v2 runtime-candidate JSONL telemetry."
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to var/data/voice_engine_v2_runtime_candidates.jsonl.",
    )
    parser.add_argument(
        "--require-accepted-intent",
        action="append",
        default=[],
        help=(
            "Require at least one accepted record for an intent. "
            "Can be used multiple times or with comma-separated values."
        ),
    )
    parser.add_argument(
        "--allow-accepted-intent",
        action="append",
        default=[],
        help=(
            "Override allowed accepted intents. "
            "Can be used multiple times or with comma-separated values."
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

    allowed = parse_intent_list(args.allow_accepted_intent)
    if not allowed:
        allowed = DEFAULT_ALLOWED_ACCEPTED_INTENTS

    required = parse_intent_list(args.require_accepted_intent)

    result = validate_runtime_candidate_log(
        args.log_path,
        allowed_accepted_intents=allowed,
        required_accepted_intents=required,
        require_records=not args.allow_empty,
    )

    print(json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
