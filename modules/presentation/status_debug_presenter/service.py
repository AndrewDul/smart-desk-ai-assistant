from __future__ import annotations

from typing import Any

from .models import StatusDebugPresentation


class StatusDebugPresenterService:
    def build_status_presentation(
        self,
        *,
        language: str,
        runtime_status_spoken: str,
        runtime_status_lines: list[str],
        benchmark_spoken: str,
        runtime_metadata: dict[str, Any],
        focus_on: bool,
        break_on: bool,
        current_timer: str,
        memory_count: int,
        reminder_count: int,
        timer_running: bool,
    ) -> StatusDebugPresentation:
        feature_spoken, feature_lines = self._feature_summary(
            language=language,
            focus_on=focus_on,
            break_on=break_on,
            current_timer=current_timer,
            memory_count=memory_count,
            reminder_count=reminder_count,
            timer_running=timer_running,
        )

        completed_turn_lines = list(runtime_metadata.get("completed_turn_lines", []) or [])
        spoken = f"{runtime_status_spoken} {benchmark_spoken} {feature_spoken}".strip()
        display_lines = runtime_status_lines[:2] + completed_turn_lines[:1] + feature_lines[:3]

        return StatusDebugPresentation(
            spoken_text=spoken,
            display_lines=display_lines,
            metadata={
                "feature_lines": feature_lines,
                "completed_turn_lines": completed_turn_lines,
            },
        )

    def build_debug_status_presentation(
        self,
        *,
        language: str,
        runtime_status_spoken: str,
        benchmark_spoken: str,
        runtime_metadata: dict[str, Any],
        audio_snapshot: dict[str, Any],
    ) -> StatusDebugPresentation:
        audio_lines = self.audio_debug_lines(language, audio_snapshot)
        debug_lines = self.debug_status_lines(language, runtime_metadata) + audio_lines

        debug_snapshot = dict(runtime_metadata.get("runtime_debug_snapshot", {}) or {})
        benchmark_snapshot = dict(runtime_metadata.get("benchmark_snapshot", {}) or {})
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})

        overlay_lines = [
            str(item).strip()
            for item in debug_snapshot.get("developer_overlay_lines", [])
            if str(item).strip()
        ]
        if not overlay_lines:
            overlay_lines = [
                str(item).strip()
                for item in benchmark_snapshot.get("overlay_lines", [])
                if str(item).strip()
            ]

        completed_turn_trace = dict(runtime_metadata.get("completed_turn_trace", {}) or {})
        completed_turn_phrase = self.completed_turn_trace_phrase(language, completed_turn_trace)
        completed_turn_lines = list(
            runtime_metadata.get("completed_turn_lines", [])
            or self.completed_turn_trace_lines(language, completed_turn_trace)
        )
        audio_phrase = self.audio_debug_phrase(language, audio_snapshot)

        if language == "pl":
            spoken = (
                f"To jest techniczny status debug. {runtime_status_spoken} {benchmark_spoken} "
                f"{audio_phrase} "
                f"{completed_turn_phrase} "
                f"Ostatni wynik to {str(latest_sample.get('result', 'brak') or 'brak')}. "
                f"Debug overlay ma {len(overlay_lines)} linie."
            )
        else:
            spoken = (
                f"This is the technical debug status. {runtime_status_spoken} {benchmark_spoken} "
                f"{audio_phrase} "
                f"{completed_turn_phrase} "
                f"The latest result is {str(latest_sample.get('result', 'n/a') or 'n/a')}. "
                f"The debug overlay contains {len(overlay_lines)} lines."
            )

        display_lines = overlay_lines[:2] if overlay_lines else (completed_turn_lines[:2] or debug_lines[:2])
        while len(display_lines) < 2 and len(debug_lines) > len(display_lines):
            display_lines.append(debug_lines[len(display_lines)])

        return StatusDebugPresentation(
            spoken_text=spoken.strip(),
            display_lines=display_lines[:2],
            metadata={
                "overlay_lines": overlay_lines,
                "debug_lines": debug_lines,
                "audio_lines": audio_lines,
                "completed_turn_trace": completed_turn_trace,
                "completed_turn_lines": completed_turn_lines,
            },
        )

    def build_status_metadata(
        self,
        *,
        resolved_source: str,
        timer_running: bool,
        focus_mode: bool,
        break_mode: bool,
        memory_count: int,
        reminder_count: int,
        current_timer: str,
        audio_runtime_snapshot: dict[str, Any],
        runtime_debug_snapshot: dict[str, Any],
        runtime_status_metadata: dict[str, Any],
        runtime_metadata: dict[str, Any],
        presentation_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "resolved_source": resolved_source,
            "timer_running": timer_running,
            "focus_mode": focus_mode,
            "break_mode": break_mode,
            "memory_count": memory_count,
            "reminder_count": reminder_count,
            "current_timer": str(current_timer),
            "audio_runtime_snapshot": dict(audio_runtime_snapshot or {}),
            "runtime_debug_snapshot": dict(runtime_debug_snapshot or {}),
        }
        metadata.update(dict(runtime_status_metadata or {}))
        metadata.update(dict(runtime_metadata or {}))
        metadata.update(dict(presentation_metadata or {}))
        return metadata

    def build_debug_status_metadata(
        self,
        *,
        resolved_source: str,
        audio_runtime_snapshot: dict[str, Any],
        runtime_debug_snapshot: dict[str, Any],
        runtime_status_metadata: dict[str, Any],
        runtime_metadata: dict[str, Any],
        presentation_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "resolved_source": resolved_source,
            "audio_runtime_snapshot": dict(audio_runtime_snapshot or {}),
            "runtime_debug_snapshot": dict(runtime_debug_snapshot or {}),
        }
        metadata.update(dict(runtime_status_metadata or {}))
        metadata.update(dict(runtime_metadata or {}))
        metadata.update(dict(presentation_metadata or {}))
        return metadata

    def audio_debug_lines(self, language: str, audio_snapshot: dict[str, Any]) -> list[str]:
        phase = self._audio_token(audio_snapshot.get("interaction_phase", "n/a"))
        owner = self._audio_token(audio_snapshot.get("input_owner", "n/a"))
        resume_action = self._audio_token(
            dict(audio_snapshot.get("last_resume_policy", {}) or {}).get("action", "n/a"),
            10,
        )
        command_action = self._audio_token(
            dict(audio_snapshot.get("last_command_window_policy", {}) or {}).get("action", "n/a"),
            10,
        )
        handoff_owner = self._audio_token(
            dict(audio_snapshot.get("last_capture_handoff", {}) or {}).get("applied_owner", "n/a"),
            14,
        )

        if language == "pl":
            return [
                f"faza: {phase}",
                f"owner: {owner}",
                f"resume: {resume_action}",
                f"cmd: {command_action}",
                f"handoff: {handoff_owner}",
            ]
        return [
            f"phase: {phase}",
            f"owner: {owner}",
            f"resume: {resume_action}",
            f"cmd: {command_action}",
            f"handoff: {handoff_owner}",
        ]

    def audio_debug_phrase(self, language: str, audio_snapshot: dict[str, Any]) -> str:
        phase = self._audio_token(audio_snapshot.get("interaction_phase", "n/a"))
        owner = self._audio_token(audio_snapshot.get("input_owner", "n/a"))
        resume_action = self._audio_token(
            dict(audio_snapshot.get("last_resume_policy", {}) or {}).get("action", "n/a"),
            10,
        )
        command_action = self._audio_token(
            dict(audio_snapshot.get("last_command_window_policy", {}) or {}).get("action", "n/a"),
            10,
        )

        if language == "pl":
            return (
                f"Audio phase to {phase}, input owner to {owner}, "
                f"ostatnia decyzja resume to {resume_action}, "
                f"a ostatnia decyzja command window to {command_action}."
            )
        return (
            f"The audio phase is {phase}, the input owner is {owner}, "
            f"the latest resume action is {resume_action}, "
            f"and the latest command window action is {command_action}."
        )

    def completed_turn_trace_phrase(self, language: str, trace: dict[str, Any]) -> str:
        route_kind = str(trace.get("route_kind", "") or "n/a")[:14]
        result = str(trace.get("result", "") or "n/a")[:24]
        resume_action = str(trace.get("resume_action", "") or "n/a")[:14]
        command_action = str(trace.get("command_action", "") or "n/a")[:14]

        if language == "pl":
            return (
                f"Ostatni zakończony turn zakończył się wynikiem {result} "
                f"na ścieżce {route_kind}, z decyzją resume {resume_action} "
                f"i command window {command_action}."
            )
        return (
            f"The latest completed turn ended with result {result} "
            f"on the {route_kind} route, with resume {resume_action} "
            f"and command window {command_action}."
        )

    def completed_turn_trace_lines(self, language: str, trace: dict[str, Any]) -> list[str]:
        route_kind = str(trace.get("route_kind", "") or "n/a")[:12]
        result = str(trace.get("result", "") or "n/a")[:16]
        resume_action = str(trace.get("resume_action", "") or "n/a")[:12]
        command_action = str(trace.get("command_action", "") or "n/a")[:12]
        command_phase = str(trace.get("command_phase", "") or "n/a")[:12]

        if language == "pl":
            return [
                f"trace: {route_kind}",
                f"wynik: {result}",
                f"resume: {resume_action}",
                f"cmd: {command_action}",
                f"faza: {command_phase}",
            ]
        return [
            f"trace: {route_kind}",
            f"result: {result}",
            f"resume: {resume_action}",
            f"cmd: {command_action}",
            f"phase: {command_phase}",
        ]

    def debug_status_lines(self, language: str, metadata: dict[str, Any]) -> list[str]:
        latest_sample = dict(metadata.get("benchmark_snapshot", {}).get("latest_sample", {}) or {})
        summary = dict(metadata.get("benchmark_snapshot", {}).get("summary", {}) or {})
        runtime_snapshot = dict(metadata.get("runtime_snapshot", {}) or {})

        route_kind = str(latest_sample.get("route_kind", "") or "n/a")[:12]
        result = str(latest_sample.get("result", "") or "n/a")[:12]
        startup_mode = str(
            runtime_snapshot.get("startup_mode", "")
            or runtime_snapshot.get("lifecycle_state", "n/a")
        )[:12]
        avg_audio_ms = metadata.get("avg_response_first_audio_ms")
        avg_llm_ms = metadata.get("avg_llm_first_chunk_ms")
        avg_total_turn_ms = self._safe_metric_float(summary.get("avg_total_turn_ms"))

        if language == "pl":
            return [
                f"mode: {startup_mode}",
                f"route: {route_kind}",
                f"wynik: {result}",
                f"turn: {int(round(avg_total_turn_ms))}ms" if avg_total_turn_ms is not None else "turn: n/a",
                f"audio: {int(round(avg_audio_ms))}ms" if avg_audio_ms is not None else "audio: n/a",
                f"llm: {int(round(avg_llm_ms))}ms" if avg_llm_ms is not None else "llm: n/a",
            ]
        return [
            f"mode: {startup_mode}",
            f"route: {route_kind}",
            f"result: {result}",
            f"turn: {int(round(avg_total_turn_ms))}ms" if avg_total_turn_ms is not None else "turn: n/a",
            f"audio: {int(round(avg_audio_ms))}ms" if avg_audio_ms is not None else "audio: n/a",
            f"llm: {int(round(avg_llm_ms))}ms" if avg_llm_ms is not None else "llm: n/a",
        ]

    def _feature_summary(
        self,
        *,
        language: str,
        focus_on: bool,
        break_on: bool,
        current_timer: str,
        memory_count: int,
        reminder_count: int,
        timer_running: bool,
    ) -> tuple[str, list[str]]:
        if language == "pl":
            spoken = (
                f"Focus jest {'włączony' if focus_on else 'wyłączony'}, "
                f"przerwa jest {'włączona' if break_on else 'wyłączona'}, "
                f"aktywny timer to {current_timer}, "
                f"w pamięci mam {memory_count} wpisów, "
                f"a przypomnień jest {reminder_count}."
            )
            lines = [
                f"focus: {'ON' if focus_on else 'OFF'}",
                f"break: {'ON' if break_on else 'OFF'}",
                f"timer: {str(current_timer)[:12]}",
                f"pamiec: {memory_count}",
                f"przyp: {reminder_count}",
                f"run: {'TAK' if timer_running else 'NIE'}",
            ]
            return spoken, lines

        spoken = (
            f"Focus is {'on' if focus_on else 'off'}, "
            f"break is {'on' if break_on else 'off'}, "
            f"the current timer is {current_timer}, "
            f"I have {memory_count} memory items, "
            f"and there are {reminder_count} reminders."
        )
        lines = [
            f"focus: {'ON' if focus_on else 'OFF'}",
            f"break: {'ON' if break_on else 'OFF'}",
            f"timer: {str(current_timer)[:12]}",
            f"memory: {memory_count}",
            f"remind: {reminder_count}",
            f"run: {'YES' if timer_running else 'NO'}",
        ]
        return spoken, lines

    @staticmethod
    def _audio_token(value: Any, max_chars: int = 14) -> str:
        compact = " ".join(str(value or "n/a").split()).strip().lower() or "n/a"
        return compact[:max_chars]

    @staticmethod
    def _safe_metric_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0.0:
            return None
        return parsed


__all__ = ["StatusDebugPresenterService"]