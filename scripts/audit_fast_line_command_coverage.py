from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.devices.audio.command_asr.command_grammar import build_default_command_grammar
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.runtime.voice_engine_v2.runtime_candidate_executor import RuntimeCandidateExecutionPlanBuilder


TARGET_FAST_INTENTS: dict[str, str] = {
    "visual_shell.show_desktop": "Show desktop.",
    "visual_shell.show_shell": "Hide desktop / return to shell.",
    "visual_shell.show_face": "Show face/self.",
    "visual_shell.look_at_user": "Look at user.",
    "visual_shell.return_to_idle": "Return to idle cloud.",
    "visual_shell.show_temperature": "Show temperature glyph.",
    "visual_shell.show_battery": "Show battery glyph.",
    "visual_shell.show_time": "Show time glyph.",
    "visual_shell.show_date": "Show date glyph.",
    "system.current_time": "Speak current time.",
    "system.current_date": "Speak current date.",
    "system.temperature": "Speak system temperature.",
    "system.battery": "Speak battery level.",
    "assistant.help": "Speak help.",
    "assistant.identity": "Speak identity.",
    "mobile_base.drive_mode": "Enter safety-gated drive mode.",
    "mobile_base.stop": "Stop mobile base.",
}


def load_runtime_allowlist() -> set[str]:
    settings_path = REPO_ROOT / "config/settings.json"
    if not settings_path.exists():
        return set()

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    values = settings.get("voice_engine", {}).get("runtime_candidate_intent_allowlist", [])
    return {str(value).strip() for value in values if str(value).strip()}


def collect_grammar_rows() -> dict[str, dict[str, Any]]:
    grammar = build_default_command_grammar()
    rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "pl": [],
            "en": [],
            "phrase_count": 0,
        }
    )

    for phrase in grammar.phrases:
        row = rows[phrase.intent_key]
        row["phrase_count"] += 1

        if phrase.language == CommandLanguage.POLISH:
            row["pl"].append(phrase.phrase)
        elif phrase.language == CommandLanguage.ENGLISH:
            row["en"].append(phrase.phrase)

    return rows


def collect_specs() -> dict[str, Any]:
    builder = RuntimeCandidateExecutionPlanBuilder()
    return dict(getattr(builder, "_SPECS", {}))


def status_for(*, has_phrases: bool, allowlisted: bool, has_spec: bool) -> str:
    if has_phrases and allowlisted and has_spec:
        return "READY"
    if not has_phrases and not allowlisted and not has_spec:
        return "MISSING"
    return "PARTIAL"


def reason_for(*, pl_count: int, en_count: int, allowlisted: bool, has_spec: bool) -> str:
    missing: list[str] = []

    if pl_count == 0:
        missing.append("PL aliases")
    if en_count == 0:
        missing.append("EN aliases")
    if not allowlisted:
        missing.append("runtime allowlist")
    if not has_spec:
        missing.append("execution spec")

    if not missing:
        return "grammar + allowlist + execution spec present"

    return "missing: " + ", ".join(missing)


def main() -> int:
    grammar_rows = collect_grammar_rows()
    allowlist = load_runtime_allowlist()
    specs = collect_specs()

    intents = sorted(set(TARGET_FAST_INTENTS) | set(grammar_rows) | set(allowlist) | set(specs))

    records: list[dict[str, Any]] = []

    for intent in intents:
        row = grammar_rows.get(intent, {"pl": [], "en": [], "phrase_count": 0})
        pl_aliases = row["pl"]
        en_aliases = row["en"]

        allowlisted = intent in allowlist
        has_spec = intent in specs
        has_phrases = row["phrase_count"] > 0

        status = status_for(
            has_phrases=has_phrases,
            allowlisted=allowlisted,
            has_spec=has_spec,
        )

        spec = specs.get(intent)
        records.append(
            {
                "intent": intent,
                "target_fast_line": intent in TARGET_FAST_INTENTS,
                "description": TARGET_FAST_INTENTS.get(intent, ""),
                "status": status,
                "reason": reason_for(
                    pl_count=len(pl_aliases),
                    en_count=len(en_aliases),
                    allowlisted=allowlisted,
                    has_spec=has_spec,
                ),
                "pl_phrase_count": len(pl_aliases),
                "en_phrase_count": len(en_aliases),
                "sample_pl_aliases": pl_aliases[:5],
                "sample_en_aliases": en_aliases[:5],
                "allowlisted": allowlisted,
                "has_execution_spec": has_spec,
                "legacy_action": getattr(spec, "legacy_action", "") if spec else "",
                "tool_name": getattr(spec, "tool_name", "") if spec else "",
            }
        )

    order = {"PARTIAL": 0, "MISSING": 1, "READY": 2}
    records.sort(key=lambda item: (not item["target_fast_line"], order[item["status"]], item["intent"]))

    report_dir = REPO_ROOT / "var/reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = {
        "generated_at_utc": generated_at,
        "summary": {
            "checked": len(records),
            "target_fast_line": sum(1 for item in records if item["target_fast_line"]),
            "ready": sum(1 for item in records if item["status"] == "READY"),
            "partial": sum(1 for item in records if item["status"] == "PARTIAL"),
            "missing": sum(1 for item in records if item["status"] == "MISSING"),
        },
        "records": records,
    }

    json_path = report_dir / "fast_line_command_coverage.json"
    md_path = report_dir / "fast_line_command_coverage.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Fast-Line Command Coverage Audit",
        "",
        f"Generated at UTC: `{generated_at}`",
        "",
        "## Summary",
        "",
        f"- Checked: {payload['summary']['checked']}",
        f"- Target fast-line: {payload['summary']['target_fast_line']}",
        f"- Ready: {payload['summary']['ready']}",
        f"- Partial: {payload['summary']['partial']}",
        f"- Missing: {payload['summary']['missing']}",
        "",
        "## Target Fast-Line Commands",
        "",
        "| Status | Intent | PL | EN | Allowlist | Spec | Reason |",
        "|---|---|---:|---:|---|---|---|",
    ]

    for item in records:
        if not item["target_fast_line"]:
            continue

        lines.append(
            f"| {item['status']} | `{item['intent']}` | "
            f"{item['pl_phrase_count']} | {item['en_phrase_count']} | "
            f"{item['allowlisted']} | {item['has_execution_spec']} | {item['reason']} |"
        )

    lines += [
        "",
        "## First Gaps To Fix",
        "",
    ]

    gaps = [item for item in records if item["target_fast_line"] and item["status"] != "READY"]
    if gaps:
        for item in gaps[:12]:
            lines.append(f"- `{item['intent']}`: {item['reason']}")
    else:
        lines.append("- No target fast-line gaps detected by this static audit.")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote: {md_path.relative_to(REPO_ROOT)}")
    print(f"Wrote: {json_path.relative_to(REPO_ROOT)}")
    print(
        "Summary: "
        f"ready={payload['summary']['ready']} "
        f"partial={payload['summary']['partial']} "
        f"missing={payload['summary']['missing']}"
    )

    print()
    print("Top target fast-line gaps:")
    for item in gaps[:10]:
        print(f"- {item['status']:7} {item['intent']}: {item['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
