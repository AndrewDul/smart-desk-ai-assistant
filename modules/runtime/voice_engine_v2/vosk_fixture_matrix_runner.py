from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.runtime.voice_engine_v2.vosk_fixture_recognition_probe import (
    probe_vosk_fixture_recognition,
    validate_vosk_fixture_recognition_result,
)
from modules.runtime.voice_engine_v2.vosk_fixture_report_summary import (
    summarize_vosk_fixture_reports,
)


VOSK_FIXTURE_MATRIX_STAGE = "vosk_fixture_matrix_runner"
VOSK_FIXTURE_MATRIX_VERSION = "stage_24ag_v1"

DEFAULT_MATRIX_REPORT_DIR = Path("var/data/stage24ag_vosk_fixture_matrix")
DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH = Path(
    "var/data/stage24ag_vosk_fixture_matrix_summary.json"
)

DEFAULT_EN_MODEL_PATH = Path("var/models/vosk/vosk-model-small-en-us-0.15")
DEFAULT_PL_MODEL_PATH = Path("var/models/vosk/vosk-model-small-pl-0.22")

FixtureTranscriptProvider = Callable[[bytes, int, tuple[str, ...]], str]


@dataclass(frozen=True)
class VoskFixtureMatrixItem:
    fixture_id: str
    language: str
    model_path: Path
    wav_path: Path
    output_path: Path

    def to_json_dict(self) -> dict[str, str]:
        return {
            "fixture_id": self.fixture_id,
            "language": self.language,
            "model_path": str(self.model_path),
            "wav_path": str(self.wav_path),
            "output_path": str(self.output_path),
        }


def build_default_vosk_fixture_matrix(
    *,
    report_dir: Path = DEFAULT_MATRIX_REPORT_DIR,
) -> tuple[VoskFixtureMatrixItem, ...]:
    report_dir = Path(report_dir)

    return (
        VoskFixtureMatrixItem(
            fixture_id="en_show_desktop",
            language="en",
            model_path=DEFAULT_EN_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/en/en_show_desktop.wav"),
            output_path=report_dir / "en_show_desktop.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="en_hide_desktop",
            language="en",
            model_path=DEFAULT_EN_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/en/en_hide_desktop.wav"),
            output_path=report_dir / "en_hide_desktop.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="en_what_time_is_it",
            language="en",
            model_path=DEFAULT_EN_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/en/en_what_time_is_it.wav"),
            output_path=report_dir / "en_what_time_is_it.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="pl_pokaz_pulpit",
            language="pl",
            model_path=DEFAULT_PL_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/pl/pl_pokaz_pulpit.wav"),
            output_path=report_dir / "pl_pokaz_pulpit.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="pl_schowaj_pulpit",
            language="pl",
            model_path=DEFAULT_PL_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/pl/pl_schowaj_pulpit.wav"),
            output_path=report_dir / "pl_schowaj_pulpit.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="pl_ktora_godzina",
            language="pl",
            model_path=DEFAULT_PL_MODEL_PATH,
            wav_path=Path("var/data/fixtures/voice_commands/pl/pl_ktora_godzina.wav"),
            output_path=report_dir / "pl_ktora_godzina.json",
        ),
    )


def run_vosk_fixture_matrix(
    *,
    report_dir: Path = DEFAULT_MATRIX_REPORT_DIR,
    summary_output_path: Path | None = DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH,
    items: Sequence[VoskFixtureMatrixItem] | None = None,
    require_languages: tuple[str, ...] = ("en", "pl"),
    transcript_provider_by_fixture_id: (
        Mapping[str, FixtureTranscriptProvider] | None
    ) = None,
) -> dict[str, Any]:
    """Run the offline Vosk fixture matrix and aggregate the resulting reports.

    This runner only reads local WAV fixtures and local Vosk models. It does
    not start live microphone capture, does not execute commands, and does not
    integrate with the production runtime.
    """

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    matrix_items = tuple(items) if items is not None else build_default_vosk_fixture_matrix(
        report_dir=report_dir
    )
    transcript_providers = transcript_provider_by_fixture_id or {}

    run_records: list[dict[str, Any]] = []
    issues: list[str] = []

    for item in matrix_items:
        command_language = _parse_matrix_language(item.language)
        transcript_provider = transcript_providers.get(item.fixture_id)

        probe_result = probe_vosk_fixture_recognition(
            model_path=item.model_path,
            wav_path=item.wav_path,
            language=command_language,
            transcript_provider=transcript_provider,
        )
        validation = validate_vosk_fixture_recognition_result(
            result=probe_result,
            require_command_match=True,
            require_language_match=True,
        )

        report_payload: dict[str, Any] = {
            **validation,
            "action": "run_vosk_fixture_matrix_item",
            "matrix_stage": VOSK_FIXTURE_MATRIX_STAGE,
            "matrix_version": VOSK_FIXTURE_MATRIX_VERSION,
            "fixture_id": item.fixture_id,
            "language": item.language,
            "output_path": str(item.output_path),
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }

        item.output_path.parent.mkdir(parents=True, exist_ok=True)
        item.output_path.write_text(
            json.dumps(report_payload, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        item_record = _matrix_item_record(
            item=item,
            validation=validation,
            report_payload=report_payload,
        )
        run_records.append(item_record)

        if validation.get("accepted") is not True:
            issues.append(f"matrix_item_failed:{item.fixture_id}")
            for issue in validation.get("issues", []):
                issues.append(f"{item.fixture_id}:{issue}")

    summary = summarize_vosk_fixture_reports(
        report_dir=report_dir,
        require_reports=True,
        require_languages=require_languages,
    )

    if summary.get("accepted") is not True:
        issues.append("matrix_summary_not_accepted")
        for issue in summary.get("issues", []):
            issues.append(f"summary:{issue}")

    accepted = not issues
    payload: dict[str, Any] = {
        "accepted": accepted,
        "action": "run_vosk_fixture_matrix",
        "matrix_stage": VOSK_FIXTURE_MATRIX_STAGE,
        "matrix_version": VOSK_FIXTURE_MATRIX_VERSION,
        "report_dir": str(report_dir),
        "summary_output_path": (
            str(summary_output_path) if summary_output_path is not None else ""
        ),
        "total_items": len(matrix_items),
        "accepted_items": sum(1 for record in run_records if record["accepted"]),
        "failed_items": sum(1 for record in run_records if not record["accepted"]),
        "require_languages": list(require_languages),
        "items": [item.to_json_dict() for item in matrix_items],
        "run_records": run_records,
        "summary": summary,
        "issues": issues,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }

    if summary_output_path is not None:
        summary_output_path.parent.mkdir(parents=True, exist_ok=True)
        summary_output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return payload


def _matrix_item_record(
    *,
    item: VoskFixtureMatrixItem,
    validation: dict[str, Any],
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    result = report_payload.get("result", {})
    if not isinstance(result, dict):
        result = {}

    return {
        "fixture_id": item.fixture_id,
        "language": item.language,
        "accepted": validation.get("accepted") is True,
        "issues": list(validation.get("issues") or ()),
        "report_path": str(item.output_path),
        "model_path": str(item.model_path),
        "wav_path": str(item.wav_path),
        "expected_language": result.get("expected_language"),
        "command_language": result.get("command_language"),
        "command_matched": result.get("command_matched") is True,
        "command_intent_key": result.get("command_intent_key"),
        "command_matched_phrase": result.get("command_matched_phrase"),
        "transcript": result.get("transcript"),
        "elapsed_ms": result.get("elapsed_ms"),
        "vocabulary_size": result.get("vocabulary_size"),
    }


def _parse_matrix_language(language: str) -> CommandLanguage:
    try:
        return CommandLanguage(language)
    except ValueError as error:
        raise ValueError(f"Unsupported Vosk fixture matrix language: {language}") from error


__all__ = [
    "DEFAULT_EN_MODEL_PATH",
    "DEFAULT_MATRIX_REPORT_DIR",
    "DEFAULT_MATRIX_SUMMARY_OUTPUT_PATH",
    "DEFAULT_PL_MODEL_PATH",
    "FixtureTranscriptProvider",
    "VOSK_FIXTURE_MATRIX_STAGE",
    "VOSK_FIXTURE_MATRIX_VERSION",
    "VoskFixtureMatrixItem",
    "build_default_vosk_fixture_matrix",
    "run_vosk_fixture_matrix",
]