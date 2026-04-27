from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_BUILDER_CORE = PROJECT_ROOT / "modules" / "runtime" / "builder" / "core.py"


def test_runtime_builder_imports_voice_engine_v2_mixin() -> None:
    source = RUNTIME_BUILDER_CORE.read_text(encoding="utf-8")

    assert "RuntimeBuilderVoiceEngineV2Mixin" in source
    assert "from .voice_engine_v2_mixin import RuntimeBuilderVoiceEngineV2Mixin" in source


def test_runtime_builder_exposes_voice_engine_v2_in_metadata_not_backend_statuses() -> None:
    source = RUNTIME_BUILDER_CORE.read_text(encoding="utf-8")

    assert "voice_engine_v2_bundle = self._build_voice_engine_v2()" in source
    assert '"voice_engine_v2": voice_engine_v2_bundle.engine' in source
    assert '"voice_engine_v2_status": voice_engine_v2_bundle.status' in source
    assert '"voice_engine_v2_metadata": voice_engine_v2_bundle.to_metadata()' in source
    assert '"voice_engine_v2": voice_engine_v2_status' not in source




def test_runtime_builder_exposes_voice_engine_v2_acceptance_adapter_in_metadata() -> None:
    source = RUNTIME_BUILDER_CORE.read_text(encoding="utf-8")

    assert '"voice_engine_v2_acceptance_adapter": (' in source
    assert "voice_engine_v2_bundle.acceptance_adapter" in source