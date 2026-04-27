from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SHADOW_LOG_PATH = Path("var/data/voice_engine_v2_shadow.jsonl")


@dataclass(frozen=True)
class ShadowLogIssue:
    line_number: int
    code: str
    message: str


@dataclass(frozen=True)
class ShadowLogSummary:
    path: Path
    total_records: int
    valid_json_records: int
    invalid_json_records: int
    action_executed_records: int
    non_legacy_primary_records: int
    empty_transcript_records: int
    missing_legacy_route_records: int
    missing_legacy_intent_records: int
    missing_voice_engine_intent_records: int
    intent_mismatch_records: int
    route_mismatch_records: int
    fallback_records: int
    issues: tuple[ShadowLogIssue, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        return (
            self.invalid_json_records == 0
            and self.action_executed_records == 0
            and self.non_legacy_primary_records == 0
            and self.empty_transcript_records == 0
            and self.missing_legacy_route_records == 0
            and self.missing_legacy_intent_records == 0
            and self.missing_voice_engine_intent_records == 0
        )


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _routes_semantically_match(
    *,
    legacy_route: str,
    voice_engine_route: str,
    legacy_intent_key: str,
    voice_engine_intent_key: str,
) -> bool:
    if not legacy_route or not voice_engine_route:
        return False

    if legacy_route == voice_engine_route:
        return True

    if (
        legacy_route == "action"
        and voice_engine_route == "command"
        and legacy_intent_key
        and legacy_intent_key == voice_engine_intent_key
    ):
        return True

    return False


def _load_json_line(raw_line: str, line_number: int) -> tuple[dict[str, Any] | None, ShadowLogIssue | None]:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as error:
        return None, ShadowLogIssue(
            line_number=line_number,
            code="invalid_json",
            message=f"Invalid JSONL record: {error.msg}",
        )

    if not isinstance(payload, dict):
        return None, ShadowLogIssue(
            line_number=line_number,
            code="invalid_record_type",
            message="JSONL record must be an object.",
        )

    return payload, None


def validate_shadow_log(path: Path) -> ShadowLogSummary:
    issues: list[ShadowLogIssue] = []

    total_records = 0
    valid_json_records = 0
    invalid_json_records = 0
    action_executed_records = 0
    non_legacy_primary_records = 0
    empty_transcript_records = 0
    missing_legacy_route_records = 0
    missing_legacy_intent_records = 0
    missing_voice_engine_intent_records = 0
    intent_mismatch_records = 0
    route_mismatch_records = 0
    fallback_records = 0

    if not path.exists():
        return ShadowLogSummary(
            path=path,
            total_records=0,
            valid_json_records=0,
            invalid_json_records=0,
            action_executed_records=0,
            non_legacy_primary_records=0,
            empty_transcript_records=0,
            missing_legacy_route_records=0,
            missing_legacy_intent_records=0,
            missing_voice_engine_intent_records=0,
            intent_mismatch_records=0,
            route_mismatch_records=0,
            fallback_records=0,
            issues=(
                ShadowLogIssue(
                    line_number=0,
                    code="file_missing",
                    message=f"Shadow log file does not exist: {path}",
                ),
            ),
        )

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            total_records += 1
            record, issue = _load_json_line(line, line_number)
            if issue is not None:
                invalid_json_records += 1
                issues.append(issue)
                continue

            if record is None:
                invalid_json_records += 1
                continue

            valid_json_records += 1

            transcript = _as_text(record.get("transcript"))
            legacy_route = _as_text(record.get("legacy_route"))
            voice_engine_route = _as_text(record.get("voice_engine_route"))
            legacy_intent_key = _as_text(record.get("legacy_intent_key"))
            voice_engine_intent_key = _as_text(record.get("voice_engine_intent_key"))
            fallback_reason = _as_text(record.get("fallback_reason"))

            if _as_bool(record.get("action_executed")):
                action_executed_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="shadow_action_executed",
                        message="Voice Engine v2 shadow record executed an action.",
                    )
                )

            if not _as_bool(record.get("legacy_runtime_primary")):
                non_legacy_primary_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="legacy_not_primary",
                        message="Shadow telemetry must keep legacy_runtime_primary=true.",
                    )
                )

            if not transcript:
                empty_transcript_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="empty_transcript",
                        message="Shadow telemetry record has an empty transcript.",
                    )
                )

            if not legacy_route:
                missing_legacy_route_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="missing_legacy_route",
                        message="Shadow telemetry record is missing legacy_route.",
                    )
                )

            if not legacy_intent_key:
                missing_legacy_intent_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="missing_legacy_intent",
                        message="Shadow telemetry record is missing legacy_intent_key.",
                    )
                )

            if not voice_engine_intent_key:
                missing_voice_engine_intent_records += 1
                issues.append(
                    ShadowLogIssue(
                        line_number=line_number,
                        code="missing_voice_engine_intent",
                        message="Shadow telemetry record is missing voice_engine_intent_key.",
                    )
                )

            if legacy_intent_key and voice_engine_intent_key and legacy_intent_key != voice_engine_intent_key:
                intent_mismatch_records += 1

            if legacy_route and voice_engine_route and not _routes_semantically_match(
                legacy_route=legacy_route,
                voice_engine_route=voice_engine_route,
                legacy_intent_key=legacy_intent_key,
                voice_engine_intent_key=voice_engine_intent_key,
            ):
                route_mismatch_records += 1

            if fallback_reason:
                fallback_records += 1

    return ShadowLogSummary(
        path=path,
        total_records=total_records,
        valid_json_records=valid_json_records,
        invalid_json_records=invalid_json_records,
        action_executed_records=action_executed_records,
        non_legacy_primary_records=non_legacy_primary_records,
        empty_transcript_records=empty_transcript_records,
        missing_legacy_route_records=missing_legacy_route_records,
        missing_legacy_intent_records=missing_legacy_intent_records,
        missing_voice_engine_intent_records=missing_voice_engine_intent_records,
        intent_mismatch_records=intent_mismatch_records,
        route_mismatch_records=route_mismatch_records,
        fallback_records=fallback_records,
        issues=tuple(issues),
    )


def format_summary(summary: ShadowLogSummary) -> str:
    lines = [
        "Voice Engine v2 shadow telemetry validation",
        f"path: {summary.path}",
        f"accepted: {summary.accepted}",
        f"total_records: {summary.total_records}",
        f"valid_json_records: {summary.valid_json_records}",
        f"invalid_json_records: {summary.invalid_json_records}",
        f"action_executed_records: {summary.action_executed_records}",
        f"non_legacy_primary_records: {summary.non_legacy_primary_records}",
        f"empty_transcript_records: {summary.empty_transcript_records}",
        f"missing_legacy_route_records: {summary.missing_legacy_route_records}",
        f"missing_legacy_intent_records: {summary.missing_legacy_intent_records}",
        f"missing_voice_engine_intent_records: {summary.missing_voice_engine_intent_records}",
        f"intent_mismatch_records: {summary.intent_mismatch_records}",
        f"route_mismatch_records: {summary.route_mismatch_records}",
        f"fallback_records: {summary.fallback_records}",
    ]

    if summary.issues:
        lines.append("issues:")
        for issue in summary.issues:
            lines.append(
                f"- line {issue.line_number}: {issue.code}: {issue.message}"
            )

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Voice Engine v2 shadow-mode JSONL telemetry."
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_SHADOW_LOG_PATH),
        help="Path to voice_engine_v2_shadow.jsonl.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return success when the shadow log file does not exist yet.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    path = Path(args.path)
    summary = validate_shadow_log(path)

    print(format_summary(summary))

    if args.allow_missing and summary.total_records == 0:
        issue_codes = {issue.code for issue in summary.issues}
        if issue_codes == {"file_missing"}:
            return 0

    return 0 if summary.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())