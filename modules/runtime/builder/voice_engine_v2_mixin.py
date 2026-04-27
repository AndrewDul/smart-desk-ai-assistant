from __future__ import annotations

from modules.runtime.voice_engine_v2 import (
    VoiceEngineV2RuntimeBundle,
    build_voice_engine_v2_runtime,
)


class RuntimeBuilderVoiceEngineV2Mixin:
    """Build the isolated Voice Engine v2 runtime adapter."""

    def _build_voice_engine_v2(self) -> VoiceEngineV2RuntimeBundle:
        return build_voice_engine_v2_runtime(self.settings)