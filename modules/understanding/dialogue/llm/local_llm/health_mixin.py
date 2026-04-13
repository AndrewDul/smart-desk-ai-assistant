from __future__ import annotations

import time
from typing import Any

from .models import LocalLLMHealthSnapshot


class LocalLLMHealthMixin:
    def _warmup_required(self) -> bool:
        return bool(
            self.enabled
            and self.runner in self._SERVER_RUNNERS
            and self.policy.startup_warmup
        )

    def _backend_capabilities(self) -> list[str]:
        capabilities: list[str] = []

        if self.runner in self._SERVER_RUNNERS:
            capabilities.extend(["persistent_service", "healthcheck"])
        if self.policy.stream_responses:
            capabilities.append("streaming")
        if self._warmup_required():
            capabilities.append("warmup")
        if self.policy.auto_recovery_enabled and self.runner in self._SERVER_RUNNERS:
            capabilities.append("auto_recovery")
        if self.runner in self._CLI_RUNNERS or self.policy.allow_cli_fallback:
            capabilities.append("cli_fallback")

        unique: list[str] = []
        seen: set[str] = set()
        for item in capabilities:
            cleaned = str(item or "").strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)
        return unique

    def _record_backend_availability_result(
        self,
        available: bool,
        *,
        error: str = "",
    ) -> None:
        now = time.monotonic()
        self._backend_last_checked_at = now
        self._backend_available = bool(available)

        if available:
            self._backend_last_success_at = now
            self._backend_consecutive_failures = 0
            self._backend_last_error = ""
            return

        self._backend_consecutive_failures += 1
        cleaned_error = str(error or "").strip()
        self._backend_last_error = (
            cleaned_error
            or self._last_availability_error
            or self._server_availability_error
            or self._backend_last_error
        )

    def _record_warmup_result(
        self,
        *,
        ok: bool,
        error: str = "",
    ) -> None:
        self._last_warmup_ok = bool(ok)
        self._last_warmup_error = "" if ok else str(error or "").strip()

        if ok:
            self._backend_last_success_at = time.monotonic()
            if self._backend_available:
                self._backend_consecutive_failures = 0

    def _record_recovery_result(
        self,
        *,
        ok: bool,
        error: str = "",
    ) -> None:
        self._backend_last_recovery_at = time.monotonic()
        self._last_recovery_ok = bool(ok)
        self._last_recovery_error = "" if ok else str(error or "").strip()

        if ok:
            self._recovery_attempts_since_success = 0
        else:
            self._recovery_attempts_since_success += 1

    def _seconds_since(self, timestamp: float) -> float | None:
        if float(timestamp or 0.0) <= 0.0:
            return None
        return max(0.0, time.monotonic() - float(timestamp))

    def _can_attempt_auto_recovery(self) -> bool:
        if not self.enabled:
            return False
        if self.runner not in self._SERVER_RUNNERS:
            return False
        if not self.policy.auto_recovery_enabled:
            return False

        max_attempts = max(int(self.policy.max_auto_recovery_attempts), 0)
        if max_attempts <= 0:
            return False
        if self._recovery_attempts_since_success >= max_attempts:
            return False

        cooldown_seconds = max(float(self.policy.auto_recovery_cooldown_seconds), 0.0)
        if cooldown_seconds <= 0.0:
            return True

        if float(self._backend_last_recovery_at or 0.0) <= 0.0:
            return True

        elapsed = time.monotonic() - float(self._backend_last_recovery_at)
        return elapsed >= cooldown_seconds

    def _attempt_backend_recovery(self) -> tuple[bool, str]:
        if not self._can_attempt_auto_recovery():
            reason = "auto recovery is currently not allowed"
            self._record_recovery_result(ok=False, error=reason)
            return False, reason

        try:
            self.reset_backend_cache()
        except Exception as error:
            reason = f"backend cache reset failed: {error}"
            self._record_recovery_result(ok=False, error=reason)
            return False, reason

        try:
            recovered = bool(self.warmup_backend_if_enabled())
        except Exception as error:
            reason = str(error)
            self._record_recovery_result(ok=False, error=reason)
            return False, reason

        if recovered:
            self._record_recovery_result(ok=True, error="")
            return True, ""

        reason = (
            self._last_warmup_error
            or self._last_availability_error
            or self._server_availability_error
            or "backend recovery failed"
        )
        self._record_recovery_result(ok=False, error=reason)
        return False, reason

    def backend_health_snapshot(self) -> dict[str, Any]:
        available = bool(self._backend_available)
        warmup_required = self._warmup_required()
        warmup_ready = (not warmup_required) or bool(self._last_warmup_ok)

        if not self.enabled:
            state = "disabled"
            healthy = False
            health_reason = "local llm disabled"
        elif available and warmup_ready:
            state = "ready"
            healthy = True
            health_reason = f"{self.runner} ready"
        elif available:
            state = "degraded"
            healthy = False
            health_reason = "backend reachable but startup warmup is not complete"
        else:
            state = "failed"
            healthy = False
            health_reason = (
                self._backend_last_error
                or self._last_availability_error
                or self._server_availability_error
                or "local llm backend unavailable"
            )

        snapshot = LocalLLMHealthSnapshot(
            enabled=bool(self.enabled),
            runner=str(self.runner or "").strip(),
            state=state,
            available=available,
            healthy=healthy,
            warmup_required=warmup_required,
            warmup_ready=warmup_ready,
            startup_warmup_enabled=bool(self.policy.startup_warmup),
            last_error=(
                self._backend_last_error
                or self._last_warmup_error
                or self._last_availability_error
                or self._server_availability_error
                or self._last_generation_error
            ),
            health_reason=health_reason,
            last_check_age_seconds=self._seconds_since(self._backend_last_checked_at),
            last_success_age_seconds=self._seconds_since(self._backend_last_success_at),
            consecutive_failures=int(self._backend_consecutive_failures),
            recovery_allowed=self._can_attempt_auto_recovery(),
            recovery_cooldown_seconds=max(
                float(self.policy.auto_recovery_cooldown_seconds),
                0.0,
            ),
            max_auto_recovery_attempts=max(
                int(self.policy.max_auto_recovery_attempts),
                0,
            ),
            recovery_attempts_since_success=max(
                int(self._recovery_attempts_since_success),
                0,
            ),
            last_recovery_age_seconds=self._seconds_since(self._backend_last_recovery_at),
            last_recovery_ok=bool(self._last_recovery_ok),
            last_recovery_error=str(self._last_recovery_error or "").strip(),
            last_warmup_ok=bool(self._last_warmup_ok),
            last_warmup_error=str(self._last_warmup_error or "").strip(),
            last_generation_ok=bool(self._last_generation_ok),
            last_generation_latency_ms=max(
                float(self._last_generation_latency_ms or 0.0),
                0.0,
            ),
            last_first_chunk_latency_ms=max(
                float(self._last_first_chunk_latency_ms or 0.0),
                0.0,
            ),
            last_generation_source=str(self._last_generation_source or "").strip(),
            server_url=str(self.server_url or "").strip(),
            server_model_name=str(self._resolved_server_model_name() or "").strip(),
            capabilities=self._backend_capabilities(),
        )
        return snapshot.to_dict()

    def ensure_backend_ready(self, *, auto_recover: bool = False) -> dict[str, Any]:
        if not self.enabled:
            snapshot = self.backend_health_snapshot()
            snapshot.update(
                {
                    "recovery_attempted": False,
                    "recovery_ok": False,
                    "recovery_error": "",
                }
            )
            return snapshot

        available = bool(self.is_available())
        snapshot = self.backend_health_snapshot()

        needs_recovery = (not available) or (
            snapshot.get("state") == "degraded" and snapshot.get("warmup_required", False)
        )

        if not auto_recover or not needs_recovery:
            snapshot.update(
                {
                    "recovery_attempted": False,
                    "recovery_ok": False,
                    "recovery_error": "",
                }
            )
            return snapshot

        ok, error = self._attempt_backend_recovery()
        snapshot = self.backend_health_snapshot()
        snapshot.update(
            {
                "recovery_attempted": True,
                "recovery_ok": bool(ok),
                "recovery_error": str(error or "").strip(),
            }
        )
        return snapshot