from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from modules.shared.persistence.json_store import JsonStore

from .models import ProductRuntimeSnapshot, ProductServiceStatus


class RuntimeProductService:
    """
    Product-level runtime state and startup orchestration service.

    Responsibilities:
    - keep one canonical runtime product state
    - persist runtime status for product-style boot diagnostics
    - evaluate startup readiness from builder statuses + LLM availability
    - attempt lightweight backend recovery where it is safe and explicit
    """

    def __init__(
        self,
        *,
        settings: dict[str, Any] | None = None,
        persist_enabled: bool = True,
        path: str = "var/data/runtime_status.json",
        required_ready_components: tuple[str, ...] = ("voice_input", "voice_output", "display"),
        auto_recovery_components: tuple[str, ...] = ("llm",),
        treat_llm_as_required_when_enabled: bool = False,
    ) -> None:
        self.settings = settings or {}
        self.persist_enabled = bool(persist_enabled)
        self.required_ready_components = tuple(
            str(item).strip()
            for item in required_ready_components
            if str(item).strip()
        )
        self.auto_recovery_components = tuple(
            str(item).strip()
            for item in auto_recovery_components
            if str(item).strip()
        )
        self.treat_llm_as_required_when_enabled = bool(treat_llm_as_required_when_enabled)

        self._lock = threading.RLock()
        self._runtime: Any | None = None
        self._dialogue: Any | None = None
        self._store = JsonStore(path=path, default_factory=self._default_snapshot_dict)
        self._snapshot = self._default_snapshot_dict()

        if self.persist_enabled:
            self._snapshot = self._store.ensure_exists()

    def bind_runtime(self, *, runtime: Any, dialogue: Any | None = None) -> None:
        with self._lock:
            self._runtime = runtime
            self._dialogue = dialogue

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._snapshot)

    def begin_boot(self, *, startup_allowed: bool, warnings: list[str] | None = None) -> dict[str, Any]:
        snapshot = ProductRuntimeSnapshot(
            lifecycle_state="booting",
            status_message="startup checks in progress",
            ready=False,
            degraded=bool(warnings),
            startup_allowed=bool(startup_allowed),
            warnings=self._unique_texts(warnings or []),
            services=dict(self._snapshot.get("services", {}) or {}),
            updated_at_iso=self._now_iso(),
        )
        return self._replace_snapshot(snapshot)

    def evaluate_startup(
        self,
        *,
        startup_allowed: bool,
        runtime_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            services = self._collect_service_statuses_locked(auto_recover=True)
            warnings = list(runtime_warnings or [])
            blockers: list[str] = []

            for name, status in services.items():
                if status.state == "disabled":
                    continue

                if status.required and status.state == "failed":
                    blockers.append(name)
                    continue

                if status.state == "degraded":
                    warnings.append(f"{name}: degraded")
                elif status.state == "failed" and not status.required:
                    warnings.append(f"{name}: unavailable")

            warnings = self._unique_texts(warnings)
            blockers = self._unique_texts(blockers)

            ready = bool(startup_allowed) and not blockers and not warnings
            degraded = bool(startup_allowed) and not ready
            lifecycle_state = "ready" if ready else "degraded" if startup_allowed else "failed"

            if ready:
                status_message = "runtime ready"
            elif blockers:
                status_message = f"required services need attention: {', '.join(blockers[:3])}"
            elif warnings:
                status_message = f"runtime degraded: {', '.join(warnings[:2])}"
            else:
                status_message = "startup checks failed"

            snapshot = ProductRuntimeSnapshot(
                lifecycle_state=lifecycle_state,
                status_message=status_message,
                ready=ready,
                degraded=degraded,
                startup_allowed=bool(startup_allowed),
                blockers=blockers,
                warnings=warnings,
                services={name: item.to_dict() for name, item in services.items()},
                updated_at_iso=self._now_iso(),
            )
            return self._replace_snapshot(snapshot)

    def mark_booting(self, reason: str = "runtime booting") -> dict[str, Any]:
        return self._transition_lifecycle("booting", reason, ready=False, degraded=False)

    def mark_ready(self, reason: str = "runtime ready") -> dict[str, Any]:
        return self._transition_lifecycle("ready", reason, ready=True, degraded=False)

    def mark_degraded(self, reason: str = "runtime degraded") -> dict[str, Any]:
        return self._transition_lifecycle("degraded", reason, ready=False, degraded=True)

    def mark_shutting_down(self, reason: str = "runtime shutting down") -> dict[str, Any]:
        return self._transition_lifecycle("shutting_down", reason, ready=False, degraded=False)

    def mark_stopped(self, reason: str = "runtime stopped") -> dict[str, Any]:
        return self._transition_lifecycle("stopped", reason, ready=False, degraded=False)

    def mark_failed(self, reason: str = "runtime failed") -> dict[str, Any]:
        return self._transition_lifecycle("failed", reason, ready=False, degraded=True)

    def _transition_lifecycle(
        self,
        lifecycle_state: str,
        reason: str,
        *,
        ready: bool,
        degraded: bool,
    ) -> dict[str, Any]:
        with self._lock:
            snapshot = dict(self._snapshot)
            snapshot["lifecycle_state"] = str(
                lifecycle_state or snapshot.get("lifecycle_state", "created")
            ).strip()
            snapshot["status_message"] = str(
                reason or snapshot.get("status_message", "")
            ).strip()
            snapshot["ready"] = bool(ready)
            snapshot["degraded"] = bool(degraded)
            snapshot["updated_at_iso"] = self._now_iso()
            self._snapshot = snapshot

            if self.persist_enabled:
                self._store.write(self._snapshot)

            return dict(self._snapshot)

    def _collect_service_statuses_locked(self, *, auto_recover: bool) -> dict[str, ProductServiceStatus]:
        statuses: dict[str, ProductServiceStatus] = {}
        required_components = set(self.required_ready_components)

        llm_cfg = self._cfg("llm")
        if self.treat_llm_as_required_when_enabled and bool(llm_cfg.get("enabled", False)):
            required_components.add("llm")

        backend_statuses = (
            getattr(self._runtime, "backend_statuses", {})
            if self._runtime is not None
            else {}
        )

        if isinstance(backend_statuses, dict):
            for component, backend_status in backend_statuses.items():
                component_name = str(component or "").strip()
                if not component_name:
                    continue

                statuses[component_name] = self._status_from_backend_status(
                    component=component_name,
                    backend_status=backend_status,
                    required=component_name in required_components,
                )

        llm_status = self._build_llm_status(
            required="llm" in required_components,
            auto_recover=auto_recover,
        )
        if llm_status is not None:
            statuses["llm"] = llm_status

        return statuses

    def _status_from_backend_status(
        self,
        *,
        component: str,
        backend_status: Any,
        required: bool,
    ) -> ProductServiceStatus:
        ok = bool(getattr(backend_status, "ok", False))
        fallback_used = bool(getattr(backend_status, "fallback_used", False))
        backend_name = str(
            getattr(backend_status, "selected_backend", "") or "unknown"
        ).strip() or "unknown"
        detail = str(getattr(backend_status, "detail", "") or "").strip()

        if component == "wake_gate" and ok and backend_name == "compatibility_voice_input":
            state = "ready"
        elif ok and not fallback_used:
            state = "ready"
        elif ok:
            state = "degraded"
        else:
            state = "failed"

        return ProductServiceStatus(
            component=component,
            backend=backend_name,
            state=state,
            detail=detail,
            required=required,
            recoverable=component in self.auto_recovery_components,
            fallback_used=fallback_used,
            last_checked_iso=self._now_iso(),
        )

    def _build_llm_status(
        self,
        *,
        required: bool,
        auto_recover: bool,
    ) -> ProductServiceStatus | None:
        llm_cfg = self._cfg("llm")
        runner = str(llm_cfg.get("runner", "disabled") or "disabled").strip() or "disabled"

        if not bool(llm_cfg.get("enabled", False)):
            return ProductServiceStatus(
                component="llm",
                backend=runner,
                state="disabled",
                detail="disabled by config",
                required=required,
                recoverable=False,
                last_checked_iso=self._now_iso(),
            )

        local_llm = getattr(self._dialogue, "local_llm", None) if self._dialogue is not None else None
        if local_llm is None:
            return ProductServiceStatus(
                component="llm",
                backend=runner,
                state="failed",
                detail="dialogue layer has no local llm service",
                required=required,
                recoverable=False,
                last_checked_iso=self._now_iso(),
            )

        describe_backend = getattr(local_llm, "describe_backend", None)
        backend_info = {}
        if callable(describe_backend):
            try:
                payload = describe_backend()
                if isinstance(payload, dict):
                    backend_info = dict(payload)
            except Exception:
                backend_info = {}

        backend_name = str(backend_info.get("runner", runner) or runner).strip() or runner
        detail = str(
            backend_info.get("last_availability_error")
            or backend_info.get("server_availability_error")
            or backend_info.get("last_generation_error")
            or ""
        ).strip()

        recovery_attempted = False
        recovery_ok = False
        recovery_error = ""

        is_available = getattr(local_llm, "is_available", None)
        available = False
        if callable(is_available):
            try:
                available = bool(is_available())
            except Exception as error:
                available = False
                recovery_error = str(error)

        if not available and auto_recover and "llm" in self.auto_recovery_components:
            recovery_attempted = True

            reset_backend_cache = getattr(local_llm, "reset_backend_cache", None)
            if callable(reset_backend_cache):
                try:
                    reset_backend_cache()
                except Exception as error:
                    recovery_error = str(error)

            warmup_backend = getattr(local_llm, "warmup_backend_if_enabled", None)
            try:
                if callable(warmup_backend):
                    available = bool(warmup_backend())
                elif callable(is_available):
                    available = bool(is_available())
            except Exception as error:
                available = False
                recovery_error = str(error)

            recovery_ok = available

        if available:
            detail = f"{backend_name} ready"
            if recovery_attempted and recovery_ok:
                detail += " after auto-recovery"
            state = "ready"
        else:
            if not detail:
                detail = recovery_error or "local llm backend unavailable"
            state = "failed"

        return ProductServiceStatus(
            component="llm",
            backend=backend_name,
            state=state,
            detail=detail,
            required=required,
            recoverable=True,
            fallback_used=False,
            last_checked_iso=self._now_iso(),
            recovery_attempted=recovery_attempted,
            recovery_ok=recovery_ok,
            recovery_error=recovery_error,
        )

    def _replace_snapshot(self, snapshot: ProductRuntimeSnapshot) -> dict[str, Any]:
        with self._lock:
            self._snapshot = snapshot.to_dict()

            if self.persist_enabled:
                self._store.write(self._snapshot)

            return dict(self._snapshot)

    def _default_snapshot_dict(self) -> dict[str, Any]:
        return ProductRuntimeSnapshot(
            lifecycle_state="created",
            status_message="runtime service created",
            ready=False,
            degraded=False,
            startup_allowed=False,
            blockers=[],
            warnings=[],
            services={},
            updated_at_iso=self._now_iso(),
        ).to_dict()

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _unique_texts(items: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for item in items:
            cleaned = " ".join(str(item or "").split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)

        return result

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = ["RuntimeProductService"]