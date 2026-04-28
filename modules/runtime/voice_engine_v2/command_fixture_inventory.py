from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import wave
from typing import Any


COMMAND_FIXTURE_INVENTORY_STAGE = "command_fixture_inventory"
COMMAND_FIXTURE_INVENTORY_VERSION = "stage_24ac_v1"

DEFAULT_FIXTURE_ROOT = Path("var/data/fixtures/voice_commands")
EXPECTED_SAMPLE_RATE = 16_000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH_BYTES = 2
DEFAULT_MAX_DURATION_MS = 5_000.0

_ALLOWED_LANGUAGE_CODES = {"en", "pl"}
_FIXTURE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")


@dataclass(frozen=True, slots=True)
class WavFixtureValidationResult:
    wav_path: str
    exists: bool
    is_file: bool
    valid: bool
    reason: str
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    frame_count: int = 0
    duration_ms: float | None = None
    pcm_byte_count: int = 0
    raw_pcm_included: bool = False
    microphone_stream_started: bool = False
    runtime_integration: bool = False
    command_execution_enabled: bool = False
    faster_whisper_bypass_enabled: bool = False
    live_command_recognition_enabled: bool = False

    def __post_init__(self) -> None:
        if self.raw_pcm_included:
            raise ValueError("WAV fixture validation must not include raw PCM")
        if self.microphone_stream_started:
            raise ValueError("WAV fixture validation must not start microphone stream")
        if self.runtime_integration:
            raise ValueError("WAV fixture validation must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("WAV fixture validation must not execute commands")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("WAV fixture validation must not bypass FasterWhisper")
        if self.live_command_recognition_enabled:
            raise ValueError(
                "WAV fixture validation must not enable live command recognition"
            )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "wav_path": self.wav_path,
            "exists": self.exists,
            "is_file": self.is_file,
            "valid": self.valid,
            "reason": self.reason,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
            "duration_ms": self.duration_ms,
            "pcm_byte_count": self.pcm_byte_count,
            "raw_pcm_included": self.raw_pcm_included,
            "microphone_stream_started": self.microphone_stream_started,
            "runtime_integration": self.runtime_integration,
            "command_execution_enabled": self.command_execution_enabled,
            "faster_whisper_bypass_enabled": self.faster_whisper_bypass_enabled,
            "live_command_recognition_enabled": self.live_command_recognition_enabled,
        }


@dataclass(frozen=True, slots=True)
class CommandFixtureMetadata:
    fixture_id: str
    language: str
    phrase: str
    wav_path: str
    metadata_path: str
    sample_rate: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    duration_ms: float
    pcm_byte_count: int
    fixture_stage: str = COMMAND_FIXTURE_INVENTORY_STAGE
    fixture_version: str = COMMAND_FIXTURE_INVENTORY_VERSION
    raw_pcm_included: bool = False
    microphone_stream_started: bool = False
    runtime_integration: bool = False
    command_execution_enabled: bool = False
    faster_whisper_bypass_enabled: bool = False
    live_command_recognition_enabled: bool = False

    def __post_init__(self) -> None:
        _validate_fixture_id(self.fixture_id)
        _validate_language(self.language)
        if not self.phrase.strip():
            raise ValueError("phrase must not be empty")
        if self.raw_pcm_included:
            raise ValueError("Command fixture metadata must not include raw PCM")
        if self.microphone_stream_started:
            raise ValueError("Command fixture metadata must not start microphone stream")
        if self.runtime_integration:
            raise ValueError("Command fixture metadata must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Command fixture metadata must not execute commands")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Command fixture metadata must not bypass FasterWhisper")
        if self.live_command_recognition_enabled:
            raise ValueError(
                "Command fixture metadata must not enable live command recognition"
            )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "fixture_stage": self.fixture_stage,
            "fixture_version": self.fixture_version,
            "fixture_id": self.fixture_id,
            "language": self.language,
            "phrase": self.phrase,
            "wav_path": self.wav_path,
            "metadata_path": self.metadata_path,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
            "duration_ms": self.duration_ms,
            "pcm_byte_count": self.pcm_byte_count,
            "raw_pcm_included": self.raw_pcm_included,
            "microphone_stream_started": self.microphone_stream_started,
            "runtime_integration": self.runtime_integration,
            "command_execution_enabled": self.command_execution_enabled,
            "faster_whisper_bypass_enabled": self.faster_whisper_bypass_enabled,
            "live_command_recognition_enabled": self.live_command_recognition_enabled,
        }


def validate_wav_fixture(
    *,
    wav_path: Path,
    max_duration_ms: float = DEFAULT_MAX_DURATION_MS,
) -> WavFixtureValidationResult:
    wav_path = Path(wav_path)

    if not wav_path.exists():
        return WavFixtureValidationResult(
            wav_path=str(wav_path),
            exists=False,
            is_file=False,
            valid=False,
            reason="wav_path_missing",
        )

    if not wav_path.is_file():
        return WavFixtureValidationResult(
            wav_path=str(wav_path),
            exists=True,
            is_file=False,
            valid=False,
            reason="wav_path_not_file",
        )

    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
    except wave.Error as error:
        return WavFixtureValidationResult(
            wav_path=str(wav_path),
            exists=True,
            is_file=True,
            valid=False,
            reason=f"wav_read_failed:{error}",
        )

    duration_ms = (
        round((frame_count / sample_rate) * 1000.0, 3)
        if sample_rate > 0
        else None
    )
    pcm_byte_count = frame_count * channels * sample_width

    if channels != EXPECTED_CHANNELS:
        reason = "wav_not_mono"
        valid = False
    elif sample_width != EXPECTED_SAMPLE_WIDTH_BYTES:
        reason = "wav_not_pcm16"
        valid = False
    elif sample_rate != EXPECTED_SAMPLE_RATE:
        reason = "wav_sample_rate_unsupported"
        valid = False
    elif frame_count <= 0:
        reason = "wav_empty"
        valid = False
    elif duration_ms is not None and duration_ms > max_duration_ms:
        reason = "wav_too_long"
        valid = False
    else:
        reason = "wav_fixture_ready"
        valid = True

    return WavFixtureValidationResult(
        wav_path=str(wav_path),
        exists=True,
        is_file=True,
        valid=valid,
        reason=reason,
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        frame_count=frame_count,
        duration_ms=duration_ms,
        pcm_byte_count=pcm_byte_count,
    )


def import_command_fixture(
    *,
    source_wav_path: Path,
    fixture_id: str,
    language: str,
    phrase: str,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    overwrite: bool = False,
    max_duration_ms: float = DEFAULT_MAX_DURATION_MS,
) -> dict[str, Any]:
    _validate_fixture_id(fixture_id)
    _validate_language(language)

    if not phrase.strip():
        raise ValueError("phrase must not be empty")

    validation = validate_wav_fixture(
        wav_path=source_wav_path,
        max_duration_ms=max_duration_ms,
    )
    if not validation.valid:
        return {
            "accepted": False,
            "action": "import_command_fixture",
            "fixture_id": fixture_id,
            "language": language,
            "phrase": phrase,
            "validation": validation.to_json_dict(),
            "metadata": None,
            "issues": [validation.reason],
        }

    fixture_root = Path(fixture_root)
    language_dir = fixture_root / language
    language_dir.mkdir(parents=True, exist_ok=True)

    target_wav_path = language_dir / f"{fixture_id}.wav"
    target_metadata_path = language_dir / f"{fixture_id}.json"

    if (target_wav_path.exists() or target_metadata_path.exists()) and not overwrite:
        return {
            "accepted": False,
            "action": "import_command_fixture",
            "fixture_id": fixture_id,
            "language": language,
            "phrase": phrase,
            "validation": validation.to_json_dict(),
            "metadata": None,
            "issues": ["fixture_already_exists"],
        }

    shutil.copy2(source_wav_path, target_wav_path)

    imported_validation = validate_wav_fixture(
        wav_path=target_wav_path,
        max_duration_ms=max_duration_ms,
    )
    if not imported_validation.valid:
        return {
            "accepted": False,
            "action": "import_command_fixture",
            "fixture_id": fixture_id,
            "language": language,
            "phrase": phrase,
            "validation": imported_validation.to_json_dict(),
            "metadata": None,
            "issues": [f"imported_fixture_invalid:{imported_validation.reason}"],
        }

    metadata = CommandFixtureMetadata(
        fixture_id=fixture_id,
        language=language,
        phrase=phrase.strip(),
        wav_path=str(target_wav_path),
        metadata_path=str(target_metadata_path),
        sample_rate=int(imported_validation.sample_rate or 0),
        channels=int(imported_validation.channels or 0),
        sample_width_bytes=int(imported_validation.sample_width_bytes or 0),
        frame_count=imported_validation.frame_count,
        duration_ms=float(imported_validation.duration_ms or 0.0),
        pcm_byte_count=imported_validation.pcm_byte_count,
    )

    target_metadata_path.write_text(
        json.dumps(metadata.to_json_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "accepted": True,
        "action": "import_command_fixture",
        "fixture_id": fixture_id,
        "language": language,
        "phrase": phrase.strip(),
        "validation": imported_validation.to_json_dict(),
        "metadata": metadata.to_json_dict(),
        "issues": [],
    }


def inventory_command_fixtures(
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> dict[str, Any]:
    fixture_root = Path(fixture_root)
    records: list[dict[str, Any]] = []
    issues: list[str] = []

    if not fixture_root.exists():
        return {
            "accepted": True,
            "action": "inventory_command_fixtures",
            "fixture_root": str(fixture_root),
            "fixture_records": 0,
            "language_counts": {},
            "records": [],
            "issues": [],
        }

    for metadata_path in sorted(fixture_root.glob("*/*.json")):
        try:
            raw_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            issues.append(f"{metadata_path}:invalid_json:{error.msg}")
            continue

        if not isinstance(raw_metadata, dict):
            issues.append(f"{metadata_path}:metadata_not_object")
            continue

        wav_path = Path(str(raw_metadata.get("wav_path") or ""))
        validation = validate_wav_fixture(wav_path=wav_path)

        record = {
            "metadata_path": str(metadata_path),
            "fixture_id": str(raw_metadata.get("fixture_id") or ""),
            "language": str(raw_metadata.get("language") or ""),
            "phrase": str(raw_metadata.get("phrase") or ""),
            "wav_path": str(wav_path),
            "wav_valid": validation.valid,
            "wav_reason": validation.reason,
            "raw_pcm_included": bool(raw_metadata.get("raw_pcm_included", False)),
            "runtime_integration": bool(raw_metadata.get("runtime_integration", False)),
            "command_execution_enabled": bool(
                raw_metadata.get("command_execution_enabled", False)
            ),
            "faster_whisper_bypass_enabled": bool(
                raw_metadata.get("faster_whisper_bypass_enabled", False)
            ),
            "microphone_stream_started": bool(
                raw_metadata.get("microphone_stream_started", False)
            ),
            "live_command_recognition_enabled": bool(
                raw_metadata.get("live_command_recognition_enabled", False)
            ),
        }
        records.append(record)

        if not validation.valid:
            issues.append(f"{metadata_path}:wav_invalid:{validation.reason}")

        for safety_field in (
            "raw_pcm_included",
            "runtime_integration",
            "command_execution_enabled",
            "faster_whisper_bypass_enabled",
            "microphone_stream_started",
            "live_command_recognition_enabled",
        ):
            if record[safety_field]:
                issues.append(f"{metadata_path}:{safety_field}_must_be_false")

    language_counts: dict[str, int] = {}
    for record in records:
        language = str(record.get("language") or "unknown")
        language_counts[language] = language_counts.get(language, 0) + 1

    return {
        "accepted": not issues,
        "action": "inventory_command_fixtures",
        "fixture_root": str(fixture_root),
        "fixture_records": len(records),
        "language_counts": language_counts,
        "records": records,
        "issues": issues,
    }


def validate_command_fixture_inventory(
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    require_records: bool = False,
    require_languages: tuple[str, ...] = (),
) -> dict[str, Any]:
    inventory = inventory_command_fixtures(fixture_root=fixture_root)
    issues = list(inventory["issues"])

    if require_records and int(inventory["fixture_records"]) <= 0:
        issues.append("command_fixture_records_missing")

    language_counts = dict(inventory["language_counts"])
    for language in require_languages:
        if int(language_counts.get(language, 0)) <= 0:
            issues.append(f"command_fixture_language_missing:{language}")

    return {
        **inventory,
        "accepted": not issues,
        "required_records": require_records,
        "required_languages": list(require_languages),
        "issues": issues,
    }


def _validate_fixture_id(fixture_id: str) -> None:
    if not _FIXTURE_ID_PATTERN.match(fixture_id):
        raise ValueError(
            "fixture_id must use lowercase letters, digits, hyphen or underscore"
        )


def _validate_language(language: str) -> None:
    if language not in _ALLOWED_LANGUAGE_CODES:
        raise ValueError("language must be one of: en, pl")


__all__ = [
    "COMMAND_FIXTURE_INVENTORY_STAGE",
    "COMMAND_FIXTURE_INVENTORY_VERSION",
    "DEFAULT_FIXTURE_ROOT",
    "DEFAULT_MAX_DURATION_MS",
    "EXPECTED_CHANNELS",
    "EXPECTED_SAMPLE_RATE",
    "EXPECTED_SAMPLE_WIDTH_BYTES",
    "CommandFixtureMetadata",
    "WavFixtureValidationResult",
    "import_command_fixture",
    "inventory_command_fixtures",
    "validate_command_fixture_inventory",
    "validate_wav_fixture",
]