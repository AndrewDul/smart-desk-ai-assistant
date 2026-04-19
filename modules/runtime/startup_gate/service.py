from __future__ import annotations

from typing import Any, Mapping

from .models import BootLifecycleDecision, StartupGateDecision


class StartupGateService:
    """Resolve startup gate behavior and post-boot lifecycle state."""

    def is_boot_ready(self, snapshot: Mapping[str, Any] | None) -> bool:
        payload = dict(snapshot or {})
        if "primary_ready" in payload:
            return bool(payload.get("primary_ready", False))
        return bool(payload.get("ready", False))

    def decide_startup_gate(
        self,
        *,
        snapshot: Mapping[str, Any] | None,
        runtime_mode: str,
        startup_allowed_default: bool,
    ) -> StartupGateDecision:
        payload = dict(snapshot or {})
        normalized_mode = str(runtime_mode or "interactive").strip().lower() or "interactive"
        blockers = self._text_list(payload.get("blockers", []))
        warnings = self._text_list(payload.get("warnings", []))
        status_message = str(payload.get("status_message", "") or "").strip()
        startup_allowed = bool(payload.get("startup_allowed", startup_allowed_default))
        primary_ready = self.is_boot_ready(payload)
        premium_ready = bool(payload.get("premium_ready", False))

        abort_startup = False
        reason = status_message

        if normalized_mode == "systemd":
            if blockers:
                blocker_text = ", ".join(blockers)
                abort_startup = True
                reason = f"required runtime components unavailable: {blocker_text}"
            elif not startup_allowed:
                abort_startup = True
                reason = status_message or "startup health checks did not allow runtime start"
            elif not primary_ready:
                abort_startup = True
                if status_message:
                    reason = f"primary runtime stack is not ready: {status_message}"
                else:
                    reason = "primary runtime stack is not ready"
            else:
                reason = status_message or "systemd startup gate passed"
        else:
            reason = status_message or f"{normalized_mode} startup gate bypassed"

        return StartupGateDecision(
            runtime_mode=normalized_mode,
            startup_allowed=startup_allowed,
            primary_ready=primary_ready,
            premium_ready=premium_ready,
            blockers=blockers,
            warnings=warnings,
            abort_startup=abort_startup,
            reason=reason,
        )

    def decide_post_boot_lifecycle(
        self,
        snapshot: Mapping[str, Any] | None,
    ) -> BootLifecycleDecision:
        payload = dict(snapshot or {})
        status_message = str(payload.get("status_message", "") or "").strip()
        premium_ready = bool(payload.get("premium_ready", False))
        primary_ready = self.is_boot_ready(payload)
        degraded = bool(payload.get("degraded", False))
        startup_allowed = bool(payload.get("startup_allowed", primary_ready))

        if premium_ready:
            return BootLifecycleDecision(
                method_name="mark_ready",
                reason="assistant boot completed",
            )

        if primary_ready or degraded or startup_allowed:
            return BootLifecycleDecision(
                method_name="mark_degraded",
                reason=status_message or "assistant boot completed in degraded mode",
            )

        return BootLifecycleDecision(
            method_name="mark_failed",
            reason=status_message or "assistant boot failed",
        )

    @staticmethod
    def _text_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []

        return [
            str(item).strip()
            for item in values
            if str(item).strip()
        ]