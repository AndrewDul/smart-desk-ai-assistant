from __future__ import annotations

import shutil
from pathlib import Path


class TTSPipelineResolutionMixin:
    """
    Helpers for resolving project paths, Piper model files, and playback tools.
    """

    def _resolve_project_path(self, raw_path: str) -> Path:
        candidate = Path(str(raw_path or "").strip())
        if candidate.is_absolute():
            return candidate
        return self._base_dir / candidate

    @staticmethod
    def _paths_ready(model_info: dict[str, Path]) -> bool:
        return model_info["model"].exists() and model_info["config"].exists()

    def _resolve_piper_paths(self) -> dict[str, dict[str, Path]]:
        resolved: dict[str, dict[str, Path]] = {}

        for lang, model_info in self.piper_models.items():
            if not isinstance(model_info, dict):
                continue

            model_raw = str(model_info.get("model", "")).strip()
            config_raw = str(model_info.get("config", "")).strip()

            resolved[self._normalize_language(lang)] = {
                "model": (
                    self._resolve_project_path(model_raw)
                    if model_raw
                    else self._base_dir / "__missing_model__"
                ),
                "config": (
                    self._resolve_project_path(config_raw)
                    if config_raw
                    else self._base_dir / "__missing_config__"
                ),
            }

        return resolved

    def _detect_playback_backends(self) -> list[tuple[str, list[str]]]:
        detected: list[tuple[str, list[str]]] = []

        pw_play = shutil.which("pw-play")
        if pw_play:
            detected.append(("pw-play", [pw_play]))

        paplay = shutil.which("paplay")
        if paplay:
            detected.append(("paplay", [paplay]))

        aplay = shutil.which("aplay")
        if aplay:
            detected.append(("aplay", [aplay]))

        ffplay = shutil.which("ffplay")
        if ffplay:
            detected.append(("ffplay", [ffplay, "-autoexit", "-nodisp"]))

        return detected

    def _piper_model_ready(self, lang: str) -> bool:
        normalized = self._normalize_language(lang)
        cached = self._piper_ready_cache.get(normalized)
        if cached is not None:
            return cached

        model_info = self._resolved_piper_paths.get(normalized)
        ready = bool(model_info and self._paths_ready(model_info))
        self._piper_ready_cache[normalized] = ready
        return ready


__all__ = ["TTSPipelineResolutionMixin"]