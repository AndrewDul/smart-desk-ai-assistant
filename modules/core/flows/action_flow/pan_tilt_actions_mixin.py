from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RuntimeBackendStatus
from modules.shared.logging.logger import get_logger


LOGGER = get_logger(__name__)


class ActionPanTiltActionsMixin:
    _DIRECTION_LABELS = {
        "pl": {
            "left": "w lewo",
            "right": "w prawo",
            "up": "w górę",
            "down": "w dół",
        },
        "en": {
            "left": "left",
            "right": "right",
            "up": "up",
            "down": "down",
        },
    }

    def _recover_pan_tilt_backend(self) -> Any | None:
        assistant = self.assistant
        config = dict(getattr(assistant, "settings", {}).get("pan_tilt", {}) or {})

        if not bool(config.get("enabled", False)):
            LOGGER.warning("Pan/tilt recovery skipped because pan_tilt.enabled is false.")
            return None

        try:
            from modules.devices.pan_tilt import PanTiltService

            old_backend = getattr(assistant, "pan_tilt", None)
            recovered_backend = PanTiltService(config=config)

            assistant.pan_tilt = recovered_backend

            runtime = getattr(assistant, "runtime", None)
            if runtime is not None:
                metadata = getattr(runtime, "metadata", None)
                if isinstance(metadata, dict):
                    metadata["pan_tilt_backend"] = recovered_backend

            backend_statuses = getattr(assistant, "backend_statuses", None)
            if isinstance(backend_statuses, dict):
                backend_statuses["pan_tilt"] = RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=True,
                    selected_backend="pca9685_pan_tilt",
                    detail="Pan/tilt backend recovered on demand from action flow.",
                    fallback_used=False,
                )

            if old_backend is not None and old_backend is not recovered_backend:
                close_method = getattr(old_backend, "close", None)
                if callable(close_method):
                    try:
                        close_method()
                    except Exception:
                        pass

            LOGGER.info(
                "Pan/tilt backend recovered successfully from action flow. backend=%s",
                recovered_backend.__class__.__name__,
            )
            return recovered_backend

        except Exception as error:
            LOGGER.exception("Pan/tilt backend recovery failed: %s", error)
            return None

    def _resolve_pan_tilt_backend(self) -> Any | None:
        backend = getattr(self.assistant, "pan_tilt", None)
        move_method = getattr(backend, "move_direction", None)

        if callable(move_method):
            return backend

        recovered = self._recover_pan_tilt_backend()
        if recovered is not None:
            return recovered

        return None

    def _should_retry_pan_tilt_with_recovery(self, result: Any, backend: Any) -> bool:
        backend_name = backend.__class__.__name__ if backend is not None else "none"
        message = self._result_message(result).lower()

        if backend_name == "NullPanTiltBackend":
            return True

        if "pan/tilt disabled" in message:
            return True
        if "movement unavailable" in message:
            return True
        if "unavailable" in message:
            return True

        return False

    def _handle_look_direction(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved,
    ) -> bool:
        del route
        direction = str(payload.get("direction", "")).strip().lower()

        backend = self._resolve_pan_tilt_backend()
        if backend is None:
            return self._deliver_feature_unavailable(language=language, action="look_direction")

        move_method = getattr(backend, "move_direction", None)
        if not callable(move_method):
            return self._deliver_feature_unavailable(language=language, action="look_direction")

        result = move_method(direction)

        if not self._result_ok(result) and self._should_retry_pan_tilt_with_recovery(result, backend):
            recovered = self._recover_pan_tilt_backend()
            if recovered is not None:
                retry_method = getattr(recovered, "move_direction", None)
                if callable(retry_method):
                    backend = recovered
                    result = retry_method(direction)

        if not self._result_ok(result):
            backend_name = backend.__class__.__name__ if backend is not None else "none"
            return self._deliver_simple_action_response(
                language=language,
                action="look_direction",
                spoken_text=self._localized(
                    language,
                    "Nie mogę teraz poruszyć platformą kamery.",
                    "I cannot move the camera platform right now.",
                ),
                display_title=self._localized(language, "PLATFORMA", "PLATFORM"),
                display_lines=self._localized_lines(
                    language,
                    ["ruch niedostepny"],
                    ["movement unavailable"],
                ),
                extra_metadata={
                    "resolved_source": resolved.source,
                    "direction": direction,
                    "error": self._result_message(result),
                    "backend": backend_name,
                },
            )

        direction_label = self._DIRECTION_LABELS[language].get(direction, direction)
        pan_angle = result.get("pan_angle")
        tilt_angle = result.get("tilt_angle")

        lines = [direction_label]
        if isinstance(pan_angle, (int, float)):
            lines.append(f"pan {pan_angle:.0f}")
        if isinstance(tilt_angle, (int, float)):
            lines.append(f"tilt {tilt_angle:.0f}")

        spoken = self._localized(
            language,
            f"Już. Patrzę {direction_label}.",
            f"Done. Looking {direction_label}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="look_direction",
            spoken_text=spoken,
            display_title=self._localized(language, "KIERUNEK", "DIRECTION"),
            display_lines=lines,
            extra_metadata={
                "resolved_source": resolved.source,
                "direction": direction,
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle,
                "backend": backend.__class__.__name__ if backend is not None else "none",
            },
        )