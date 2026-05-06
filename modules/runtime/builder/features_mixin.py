from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus


class RuntimeBuilderFeaturesMixin:
    """
    Build the core feature services.
    """

    def _build_memory(self) -> Any:
        memory_class = self._import_symbol(
            "modules.features.memory.service",
            "MemoryService",
        )
        return memory_class()

    def _build_reminders(self) -> Any:
        reminders_class = self._import_symbol(
            "modules.features.reminders.service",
            "ReminderService",
        )
        return reminders_class()

    def _build_timer(
        self,
        *,
        on_timer_started=None,
        on_timer_finished=None,
        on_timer_stopped=None,
        on_timer_tick=None,
    ) -> Any:
        timer_class = self._import_symbol(
            "modules.features.timer.service",
            "TimerService",
        )
        return timer_class(
            on_started=on_timer_started,
            on_finished=on_timer_finished,
            on_stopped=on_timer_stopped,
            on_tick=on_timer_tick,
        )

    def _build_focus_vision(
        self,
        config: dict[str, object],
        *,
        vision_backend: Any,
    ) -> tuple[Any | None, RuntimeBackendStatus]:
        try:
            config_class = self._import_symbol(
                "modules.features.focus_vision",
                "FocusVisionConfig",
            )
            service_class = self._import_symbol(
                "modules.features.focus_vision",
                "FocusVisionSentinelService",
            )
            focus_config = config_class.from_mapping(config)
            service = service_class(
                vision_backend=vision_backend,
                config=focus_config,
            )
            service_status = service.status() if hasattr(service, "status") else {}
            if not bool(getattr(focus_config, "enabled", False)):
                return (
                    service,
                    RuntimeBackendStatus(
                        component="focus_vision",
                        ok=True,
                        selected_backend="disabled_focus_vision_sentinel",
                        detail="Focus Vision Sentinel service is built but disabled in config.",
                        runtime_mode="disabled",
                        capabilities=(
                            "focus_mode_lifecycle_hook",
                            "dry_run_telemetry",
                            "deterministic_reminder_policy",
                        ),
                        metadata=dict(service_status or {}),
                    ),
                )

            runtime_mode = "dry_run" if bool(getattr(focus_config, "dry_run", True)) else "active"
            return (
                service,
                RuntimeBackendStatus(
                    component="focus_vision",
                    ok=True,
                    selected_backend="focus_vision_sentinel_service",
                    detail=(
                        "Focus Vision Sentinel service loaded for Focus Mode lifecycle. "
                        "Pan-tilt scanning remains controlled by focus_vision.pan_tilt_scan_enabled."
                    ),
                    runtime_mode=runtime_mode,
                    capabilities=(
                        "focus_mode_lifecycle_hook",
                        "desk_presence_decision",
                        "phone_distraction_decision",
                        "dry_run_telemetry",
                        "deterministic_reminder_policy",
                        "notification_flow_delivery_gate",
                    ),
                    metadata=dict(service_status or {}),
                ),
            )
        except Exception as error:
            return (
                None,
                RuntimeBackendStatus(
                    component="focus_vision",
                    ok=False,
                    selected_backend="null_focus_vision",
                    detail=(
                        "Focus Vision Sentinel service failed to load. "
                        f"Focus Mode remains available without vision monitoring. Error: {error}"
                    ),
                    fallback_used=True,
                    runtime_mode="disabled",
                ),
            )


__all__ = ["RuntimeBuilderFeaturesMixin"]
