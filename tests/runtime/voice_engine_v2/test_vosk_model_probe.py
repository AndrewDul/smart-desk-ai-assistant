from __future__ import annotations

from pathlib import Path

import pytest

from modules.runtime.voice_engine_v2.vosk_model_probe import (
    VoskModelProbeResult,
    probe_vosk_model,
    probe_vosk_models,
)


def _create_minimal_vosk_model(path: Path) -> None:
    (path / "am").mkdir(parents=True, exist_ok=True)
    (path / "conf").mkdir(parents=True, exist_ok=True)
    (path / "am" / "final.mdl").write_text("fake model", encoding="utf-8")
    (path / "conf" / "model.conf").write_text("fake config", encoding="utf-8")


def test_probe_vosk_model_reports_missing_path_without_loading(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "missing-model"

    result = probe_vosk_model(model_path=model_path, load_model=True)

    payload = result.to_json_dict()

    assert payload["model_path"] == str(model_path)
    assert payload["exists"] is False
    assert payload["is_directory"] is False
    assert payload["structure_ready"] is False
    assert payload["load_requested"] is True
    assert payload["load_attempted"] is False
    assert payload["load_success"] is False
    assert payload["reason"] == "model_path_missing"
    assert payload["microphone_stream_started"] is False
    assert payload["command_recognition_attempted"] is False
    assert payload["raw_pcm_included"] is False


def test_probe_vosk_model_accepts_structure_without_load(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    _create_minimal_vosk_model(model_path)

    result = probe_vosk_model(model_path=model_path, load_model=False)

    payload = result.to_json_dict()

    assert payload["exists"] is True
    assert payload["is_directory"] is True
    assert payload["marker_status"] == {
        "am/final.mdl": True,
        "conf/model.conf": True,
    }
    assert payload["structure_ready"] is True
    assert payload["load_requested"] is False
    assert payload["load_attempted"] is False
    assert payload["load_success"] is False
    assert payload["reason"] == "model_structure_ready_load_not_requested"


def test_probe_vosk_model_uses_injected_loader_when_load_requested(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-pl"
    _create_minimal_vosk_model(model_path)
    loaded_paths: list[Path] = []

    def loader(path: Path) -> object:
        loaded_paths.append(path)
        return object()

    result = probe_vosk_model(
        model_path=model_path,
        load_model=True,
        model_loader=loader,
    )

    payload = result.to_json_dict()

    assert loaded_paths == [model_path]
    assert payload["structure_ready"] is True
    assert payload["load_requested"] is True
    assert payload["load_attempted"] is True
    assert payload["load_success"] is True
    assert payload["reason"] == "model_loaded"
    assert payload["load_elapsed_ms"] is not None
    assert payload["microphone_stream_started"] is False
    assert payload["command_recognition_attempted"] is False


def test_probe_vosk_model_reports_loader_failure(tmp_path: Path) -> None:
    model_path = tmp_path / "vosk-model-small-pl"
    _create_minimal_vosk_model(model_path)

    def loader(path: Path) -> object:
        raise RuntimeError("load failed")

    result = probe_vosk_model(
        model_path=model_path,
        load_model=True,
        model_loader=loader,
    )

    payload = result.to_json_dict()

    assert payload["load_requested"] is True
    assert payload["load_attempted"] is True
    assert payload["load_success"] is False
    assert payload["reason"] == "model_load_failed"
    assert "RuntimeError:load failed" == payload["load_error"]


def test_probe_vosk_models_accepts_present_model_without_load(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    _create_minimal_vosk_model(model_path)

    result = probe_vosk_models(
        model_paths=(model_path,),
        load_model=False,
        require_model_present=True,
    )

    assert result["accepted"] is True
    assert result["present_model_records"] == 1
    assert result["structure_ready_records"] == 1
    assert result["load_attempted_records"] == 0
    assert result["load_success_records"] == 0
    assert result["issues"] == []


def test_probe_vosk_models_requires_present_model(tmp_path: Path) -> None:
    result = probe_vosk_models(
        model_paths=(tmp_path / "missing",),
        require_model_present=True,
    )

    assert result["accepted"] is False
    assert "vosk_model_present_records_missing" in result["issues"]


def test_probe_vosk_models_requires_load_model_when_require_loadable(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    _create_minimal_vosk_model(model_path)

    result = probe_vosk_models(
        model_paths=(model_path,),
        load_model=False,
        require_loadable=True,
    )

    assert result["accepted"] is False
    assert "require_loadable_without_load_model" in result["issues"]
    assert "vosk_model_load_success_records_missing" in result["issues"]


def test_probe_vosk_models_accepts_injected_load_success(tmp_path: Path) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    _create_minimal_vosk_model(model_path)

    result = probe_vosk_models(
        model_paths=(model_path,),
        load_model=True,
        require_model_present=True,
        require_loadable=True,
        model_loader=lambda path: object(),
    )

    assert result["accepted"] is True
    assert result["present_model_records"] == 1
    assert result["structure_ready_records"] == 1
    assert result["load_attempted_records"] == 1
    assert result["load_success_records"] == 1
    assert result["loadable_paths"] == [str(model_path)]
    assert result["microphone_stream_records"] == 0
    assert result["command_recognition_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["issues"] == []


def test_vosk_model_probe_result_rejects_unsafe_action() -> None:
    with pytest.raises(ValueError, match="must never execute actions"):
        VoskModelProbeResult(
            model_path="model",
            exists=True,
            is_directory=True,
            marker_status={},
            structure_ready=True,
            load_requested=False,
            load_attempted=False,
            load_success=False,
            action_executed=True,
        )