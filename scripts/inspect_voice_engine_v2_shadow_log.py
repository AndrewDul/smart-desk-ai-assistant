from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_SHADOW_LOG_PATH = Path("var/data/voice_engine_v2_shadow.jsonl")


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    return bool(value)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(parsed) or math.isinf(parsed):
        return None

    return parsed


def _truncate(value: str, limit: int = 120) -> str:
    cleaned = _as_text(value).replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)] + "…"


def _nested_dict(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key, {})
    if isinstance(value, dict):
        return value
    return {}


def _record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return _nested_dict(record, "metadata")


def _record_language(record: dict[str, Any]) -> str:
    metadata = _record_metadata(record)

    for candidate in (
        record.get("language"),
        record.get("language_final"),
        record.get("language_hint"),
        record.get("voice_engine_language"),
        metadata.get("language"),
        metadata.get("language_final"),
        metadata.get("language_hint"),
        metadata.get("voice_engine_language"),
    ):
        text = _as_text(candidate)
        if text:
            return text

    return "unknown"


def _record_route_path(record: dict[str, Any]) -> str:
    metadata = _record_metadata(record)
    return _as_text(metadata.get("route_path")) or "unknown"


def _record_fallback_reason(record: dict[str, Any]) -> str:
    for candidate in (
        record.get("fallback_reason"),
        _record_metadata(record).get("fallback_reason"),
    ):
        text = _as_text(candidate)
        if text:
            return text
    return ""


def _metric_value(record: dict[str, Any], key: str) -> float | None:
    for source in (
        record,
        _nested_dict(record, "metrics"),
        _nested_dict(record, "timing"),
        _record_metadata(record),
    ):
        value = _safe_float(source.get(key))
        if value is not None:
            return value

    return None


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    rank = math.ceil((percentile / 100.0) * len(ordered))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]


def _metric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
        }

    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "p50": round(_percentile_nearest_rank(ordered, 50.0) or 0.0, 3),
        "p95": round(_percentile_nearest_rank(ordered, 95.0) or 0.0, 3),
        "max": round(ordered[-1], 3),
    }


def _counter_top(counter: Counter[str], limit: int) -> dict[str, int]:
    return {key: count for key, count in counter.most_common(max(1, limit))}


_INTENT_ALIASES = {
    "introduce_self": "assistant.identity",
    "ask_time": "system.current_time",
}


def _normalized_intent_key(value: str) -> str:
    cleaned = _as_text(value)
    return _INTENT_ALIASES.get(cleaned, cleaned)


def _intents_semantically_match(
    *,
    legacy_intent_key: str,
    voice_engine_intent_key: str,
) -> bool:
    legacy_normalized = _normalized_intent_key(legacy_intent_key)
    voice_engine_normalized = _normalized_intent_key(voice_engine_intent_key)
    return bool(legacy_normalized) and legacy_normalized == voice_engine_normalized


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
        and _intents_semantically_match(
            legacy_intent_key=legacy_intent_key,
            voice_engine_intent_key=voice_engine_intent_key,
        )
    ):
        return True

    if legacy_route == "unclear" and voice_engine_route == "fallback":
        return True

    return False


def _sample_record(record: dict[str, Any], line_number: int) -> dict[str, Any]:
    return {
        "line_number": line_number,
        "turn_id": _as_text(record.get("turn_id")),
        "transcript": _truncate(_as_text(record.get("transcript"))),
        "legacy_route": _as_text(record.get("legacy_route")),
        "voice_engine_route": _as_text(record.get("voice_engine_route")),
        "legacy_intent_key": _as_text(record.get("legacy_intent_key")),
        "voice_engine_intent_key": _as_text(record.get("voice_engine_intent_key")),
        "fallback_reason": _record_fallback_reason(record),
        "route_path": _record_route_path(record),
        "language": _record_language(record),
    }


def _load_records(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    issues: list[dict[str, Any]] = []

    if not path.exists():
        issues.append(
            {
                "line_number": 0,
                "code": "file_missing",
                "message": f"Shadow log file does not exist: {path}",
            }
        )
        return records, issues

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append(
                    {
                        "line_number": line_number,
                        "code": "invalid_json",
                        "message": error.msg,
                    }
                )
                continue

            if not isinstance(payload, dict):
                issues.append(
                    {
                        "line_number": line_number,
                        "code": "invalid_record_type",
                        "message": "JSONL record must be an object.",
                    }
                )
                continue

            records.append((line_number, payload))

    return records, issues


def inspect_shadow_log(
    path: Path,
    *,
    sample_limit: int = 5,
    top_limit: int = 10,
) -> dict[str, Any]:
    records, load_issues = _load_records(path)

    action_executed_samples: list[dict[str, Any]] = []
    non_legacy_primary_samples: list[dict[str, Any]] = []
    intent_mismatch_samples: list[dict[str, Any]] = []
    route_mismatch_samples: list[dict[str, Any]] = []
    fallback_samples: list[dict[str, Any]] = []
    empty_transcript_samples: list[dict[str, Any]] = []

    language_counts: Counter[str] = Counter()
    route_path_counts: Counter[str] = Counter()
    legacy_route_counts: Counter[str] = Counter()
    voice_engine_route_counts: Counter[str] = Counter()
    legacy_intent_counts: Counter[str] = Counter()
    voice_engine_intent_counts: Counter[str] = Counter()
    fallback_reason_counts: Counter[str] = Counter()

    speech_end_to_action_ms: list[float] = []
    dispatch_ms: list[float] = []

    for line_number, record in records:
        transcript = _as_text(record.get("transcript"))
        legacy_route = _as_text(record.get("legacy_route"))
        voice_engine_route = _as_text(record.get("voice_engine_route"))
        legacy_intent_key = _as_text(record.get("legacy_intent_key"))
        voice_engine_intent_key = _as_text(record.get("voice_engine_intent_key"))
        fallback_reason = _record_fallback_reason(record)

        language_counts[_record_language(record)] += 1
        route_path_counts[_record_route_path(record)] += 1

        if legacy_route:
            legacy_route_counts[legacy_route] += 1
        if voice_engine_route:
            voice_engine_route_counts[voice_engine_route] += 1
        if legacy_intent_key:
            legacy_intent_counts[legacy_intent_key] += 1
        if voice_engine_intent_key:
            voice_engine_intent_counts[voice_engine_intent_key] += 1
        if fallback_reason:
            fallback_reason_counts[fallback_reason] += 1

        speech_end_metric = _metric_value(record, "speech_end_to_action_ms")
        if speech_end_metric is not None:
            speech_end_to_action_ms.append(speech_end_metric)

        dispatch_metric = _metric_value(record, "dispatch_ms")
        if dispatch_metric is not None:
            dispatch_ms.append(dispatch_metric)

        if not transcript and len(empty_transcript_samples) < sample_limit:
            empty_transcript_samples.append(_sample_record(record, line_number))

        if _as_bool(record.get("action_executed")) and len(action_executed_samples) < sample_limit:
            action_executed_samples.append(_sample_record(record, line_number))

        if not _as_bool(record.get("legacy_runtime_primary")) and len(non_legacy_primary_samples) < sample_limit:
            non_legacy_primary_samples.append(_sample_record(record, line_number))

        if (
            legacy_intent_key
            and voice_engine_intent_key
            and not _intents_semantically_match(
                legacy_intent_key=legacy_intent_key,
                voice_engine_intent_key=voice_engine_intent_key,
            )
            and len(intent_mismatch_samples) < sample_limit
        ):
            intent_mismatch_samples.append(_sample_record(record, line_number))

        if (
            legacy_route
            and voice_engine_route
            and not _routes_semantically_match(
                legacy_route=legacy_route,
                voice_engine_route=voice_engine_route,
                legacy_intent_key=legacy_intent_key,
                voice_engine_intent_key=voice_engine_intent_key,
            )
            and len(route_mismatch_samples) < sample_limit
        ):
            route_mismatch_samples.append(_sample_record(record, line_number))

        if fallback_reason and len(fallback_samples) < sample_limit:
            fallback_samples.append(_sample_record(record, line_number))

    action_executed_records = sum(
        1 for _, record in records if _as_bool(record.get("action_executed"))
    )
    non_legacy_primary_records = sum(
        1 for _, record in records if not _as_bool(record.get("legacy_runtime_primary"))
    )
    empty_transcript_records = sum(
        1 for _, record in records if not _as_text(record.get("transcript"))
    )
    intent_mismatch_records = sum(
        1
        for _, record in records
        if _as_text(record.get("legacy_intent_key"))
        and _as_text(record.get("voice_engine_intent_key"))
        and not _intents_semantically_match(
            legacy_intent_key=_as_text(record.get("legacy_intent_key")),
            voice_engine_intent_key=_as_text(record.get("voice_engine_intent_key")),
        )
    )
    route_mismatch_records = sum(
        1
        for _, record in records
        if _as_text(record.get("legacy_route"))
        and _as_text(record.get("voice_engine_route"))
        and not _routes_semantically_match(
            legacy_route=_as_text(record.get("legacy_route")),
            voice_engine_route=_as_text(record.get("voice_engine_route")),
            legacy_intent_key=_as_text(record.get("legacy_intent_key")),
            voice_engine_intent_key=_as_text(record.get("voice_engine_intent_key")),
        )
    )
    fallback_records = sum(
        1 for _, record in records if _record_fallback_reason(record)
    )

    safety_ok = (
        not load_issues
        and action_executed_records == 0
        and non_legacy_primary_records == 0
        and empty_transcript_records == 0
    )

    return {
        "path": str(path),
        "safety_ok": safety_ok,
        "total_records": len(records) + len(load_issues),
        "valid_json_records": len(records),
        "load_issue_count": len(load_issues),
        "load_issues": load_issues,
        "action_executed_records": action_executed_records,
        "non_legacy_primary_records": non_legacy_primary_records,
        "empty_transcript_records": empty_transcript_records,
        "intent_mismatch_records": intent_mismatch_records,
        "route_mismatch_records": route_mismatch_records,
        "fallback_records": fallback_records,
        "counts": {
            "language": _counter_top(language_counts, top_limit),
            "route_path": _counter_top(route_path_counts, top_limit),
            "legacy_route": _counter_top(legacy_route_counts, top_limit),
            "voice_engine_route": _counter_top(voice_engine_route_counts, top_limit),
            "legacy_intent": _counter_top(legacy_intent_counts, top_limit),
            "voice_engine_intent": _counter_top(voice_engine_intent_counts, top_limit),
            "fallback_reason": _counter_top(fallback_reason_counts, top_limit),
        },
        "latency": {
            "speech_end_to_action_ms": _metric_summary(speech_end_to_action_ms),
            "dispatch_ms": _metric_summary(dispatch_ms),
        },
        "samples": {
            "action_executed": action_executed_samples,
            "non_legacy_primary": non_legacy_primary_samples,
            "empty_transcript": empty_transcript_samples,
            "intent_mismatch": intent_mismatch_samples,
            "route_mismatch": route_mismatch_samples,
            "fallback": fallback_samples,
        },
    }


def _format_count_block(title: str, values: dict[str, int]) -> list[str]:
    lines = [f"{title}:"]
    if not values:
        lines.append("  - none")
        return lines

    for key, count in values.items():
        lines.append(f"  - {key}: {count}")
    return lines


def _format_latency_block(title: str, values: dict[str, float | int | None]) -> list[str]:
    return [
        f"{title}:",
        f"  - count: {values.get('count', 0)}",
        f"  - min: {values.get('min')}",
        f"  - p50: {values.get('p50')}",
        f"  - p95: {values.get('p95')}",
        f"  - max: {values.get('max')}",
    ]


def _format_sample_block(title: str, samples: list[dict[str, Any]]) -> list[str]:
    lines = [f"{title}:"]
    if not samples:
        lines.append("  - none")
        return lines

    for sample in samples:
        lines.append(
            "  - "
            f"line={sample['line_number']} "
            f"turn_id={sample['turn_id'] or '-'} "
            f"lang={sample['language']} "
            f"route_path={sample['route_path']} "
            f"legacy={sample['legacy_route']}:{sample['legacy_intent_key']} "
            f"voice_engine={sample['voice_engine_route']}:{sample['voice_engine_intent_key']} "
            f"fallback={sample['fallback_reason'] or '-'} "
            f"transcript=\"{sample['transcript']}\""
        )

    return lines


def format_report(summary: dict[str, Any]) -> str:
    counts = summary.get("counts", {})
    latency = summary.get("latency", {})
    samples = summary.get("samples", {})

    lines = [
        "Voice Engine v2 shadow telemetry inspection",
        f"path: {summary.get('path')}",
        f"safety_ok: {summary.get('safety_ok')}",
        f"total_records: {summary.get('total_records')}",
        f"valid_json_records: {summary.get('valid_json_records')}",
        f"load_issue_count: {summary.get('load_issue_count')}",
        f"action_executed_records: {summary.get('action_executed_records')}",
        f"non_legacy_primary_records: {summary.get('non_legacy_primary_records')}",
        f"empty_transcript_records: {summary.get('empty_transcript_records')}",
        f"intent_mismatch_records: {summary.get('intent_mismatch_records')}",
        f"route_mismatch_records: {summary.get('route_mismatch_records')}",
        f"fallback_records: {summary.get('fallback_records')}",
        "",
    ]

    lines.extend(_format_count_block("Languages", counts.get("language", {})))
    lines.append("")
    lines.extend(_format_count_block("Route paths", counts.get("route_path", {})))
    lines.append("")
    lines.extend(_format_count_block("Legacy routes", counts.get("legacy_route", {})))
    lines.append("")
    lines.extend(_format_count_block("Voice Engine routes", counts.get("voice_engine_route", {})))
    lines.append("")
    lines.extend(_format_count_block("Top legacy intents", counts.get("legacy_intent", {})))
    lines.append("")
    lines.extend(_format_count_block("Top Voice Engine intents", counts.get("voice_engine_intent", {})))
    lines.append("")
    lines.extend(_format_count_block("Fallback reasons", counts.get("fallback_reason", {})))
    lines.append("")
    lines.extend(
        _format_latency_block(
            "Latency speech_end_to_action_ms",
            latency.get("speech_end_to_action_ms", {}),
        )
    )
    lines.append("")
    lines.extend(_format_latency_block("Latency dispatch_ms", latency.get("dispatch_ms", {})))
    lines.append("")
    lines.extend(_format_sample_block("Action-executed samples", samples.get("action_executed", [])))
    lines.append("")
    lines.extend(
        _format_sample_block(
            "Non-legacy-primary samples",
            samples.get("non_legacy_primary", []),
        )
    )
    lines.append("")
    lines.extend(_format_sample_block("Empty transcript samples", samples.get("empty_transcript", [])))
    lines.append("")
    lines.extend(_format_sample_block("Intent mismatch samples", samples.get("intent_mismatch", [])))
    lines.append("")
    lines.extend(_format_sample_block("Route mismatch samples", samples.get("route_mismatch", [])))
    lines.append("")
    lines.extend(_format_sample_block("Fallback samples", samples.get("fallback", [])))

    load_issues = summary.get("load_issues", [])
    if load_issues:
        lines.append("")
        lines.append("Load issues:")
        for issue in load_issues:
            lines.append(
                f"  - line={issue.get('line_number')} "
                f"code={issue.get('code')} "
                f"message={issue.get('message')}"
            )

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Voice Engine v2 shadow-mode JSONL telemetry.",
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_SHADOW_LOG_PATH),
        help="Path to voice_engine_v2_shadow.jsonl.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Maximum sample records to print per category.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Maximum count entries to print per category.",
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
    summary = inspect_shadow_log(
        path,
        sample_limit=max(1, int(args.sample_limit or 5)),
        top_limit=max(1, int(args.top or 10)),
    )

    print(format_report(summary))

    load_issues = summary.get("load_issues", [])
    if args.allow_missing and len(load_issues) == 1:
        issue = load_issues[0]
        if issue.get("code") == "file_missing":
            return 0

    return 0 if bool(summary.get("safety_ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())