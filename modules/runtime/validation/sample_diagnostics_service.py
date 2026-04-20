from __future__ import annotations

from typing import Any

from modules.shared.config.settings import load_settings

from .service import TurnBenchmarkValidationService


class TurnBenchmarkSampleDiagnosticsService:
    """Explain how persisted benchmark samples are classified by validation rules."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.validation_service = TurnBenchmarkValidationService(settings=self.settings)

    def read_samples(self) -> list[dict[str, Any]]:
        read_result = self.validation_service._store.read_result()
        payload = read_result.value if isinstance(read_result.value, dict) else {}
        return [
            dict(item)
            for item in list(payload.get("samples", []) or [])
            if isinstance(item, dict)
        ]

    def tail(
        self,
        *,
        count: int = 10,
        only_non_llm: bool = False,
        only_skill: bool = False,
    ) -> list[dict[str, Any]]:
        samples = self.read_samples()
        if only_non_llm:
            samples = [sample for sample in samples if not self.validation_service._is_llm_turn(sample)]
        if only_skill:
            samples = [sample for sample in samples if self.validation_service._is_skill_turn(sample)]
        return samples[-max(1, int(count)) :]

    def describe_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        voice_reasons = self._voice_reasons(sample)
        llm_reasons = self._llm_reasons(sample)
        skill_reasons = self._skill_reasons(sample, llm_reasons=llm_reasons)

        is_voice = self.validation_service._is_voice_turn(sample)
        is_llm = self.validation_service._is_llm_turn(sample)
        is_skill = self.validation_service._is_skill_turn(sample)

        return {
            "turn_id": str(sample.get("turn_id", "") or "").strip(),
            "result": str(sample.get("result", "") or "").strip(),
            "input_source": str(sample.get("input_source", "") or "").strip(),
            "route_kind": str(sample.get("route_kind", "") or "").strip(),
            "primary_intent": str(sample.get("primary_intent", "") or "").strip(),
            "voice": is_voice,
            "skill": is_skill,
            "llm": is_llm,
            "voice_reasons": voice_reasons,
            "skill_reasons": skill_reasons,
            "llm_reasons": llm_reasons,
            "response_source": str(sample.get("response_source", "") or "").strip(),
            "response_reply_source": str(sample.get("response_reply_source", "") or "").strip(),
            "response_stream_mode": str(sample.get("response_stream_mode", "") or "").strip(),
            "response_live_streaming": bool(sample.get("response_live_streaming", False)),
            "dialogue_source": str(sample.get("dialogue_source", "") or "").strip(),
            "dialogue_status": str(sample.get("dialogue_status", "") or "").strip(),
            "dialogue_delivered": bool(sample.get("dialogue_delivered", False)),
            "llm_source": str(sample.get("llm_source", "") or "").strip(),
            "llm_ok": bool(sample.get("llm_ok", False)),
            "llm_first_chunk_ms": self._safe_float(sample.get("llm_first_chunk_ms")),
            "skill_handled": bool(sample.get("skill_handled", False)),
            "skill_source": str(sample.get("skill_source", "") or "").strip(),
            "skill_action": str(sample.get("skill_action", "") or "").strip(),
            "skill_status": str(sample.get("skill_status", "") or "").strip(),
            "wake_latency_ms": self._safe_float(sample.get("wake_latency_ms")),
            "stt_latency_ms": self._safe_float(sample.get("stt_latency_ms")),
            "route_to_first_audio_ms": self._safe_float(sample.get("route_to_first_audio_ms")),
            "response_first_audio_ms": self._safe_float(sample.get("response_first_audio_ms")),
            "total_turn_ms": self._safe_float(sample.get("total_turn_ms")),
        }

    def render_description(self, description: dict[str, Any]) -> str:
        labels: list[str] = []
        if description["voice"]:
            labels.append("voice")
        if description["skill"]:
            labels.append("skill")
        if description["llm"]:
            labels.append("llm")

        label_text = ", ".join(labels) if labels else "unclassified"

        def _fmt_list(values: list[str]) -> str:
            return ", ".join(values) if values else "-"

        lines = [
            f"Turn: {description['turn_id'] or '-'}",
            f"Classification: {label_text}",
            f"Result: {description['result'] or '-'}",
            f"Input: {description['input_source'] or '-'} | route_kind={description['route_kind'] or '-'} | intent={description['primary_intent'] or '-'}",
            (
                "Response: "
                f"source={description['response_source'] or '-'} | "
                f"reply_source={description['response_reply_source'] or '-'} | "
                f"stream_mode={description['response_stream_mode'] or '-'} | "
                f"live={description['response_live_streaming']}"
            ),
            (
                "Dialogue: "
                f"source={description['dialogue_source'] or '-'} | "
                f"status={description['dialogue_status'] or '-'} | "
                f"delivered={description['dialogue_delivered']}"
            ),
            (
                "LLM: "
                f"source={description['llm_source'] or '-'} | "
                f"ok={description['llm_ok']} | "
                f"first_chunk_ms={self._metric_text(description['llm_first_chunk_ms'])}"
            ),
            (
                "Skill: "
                f"handled={description['skill_handled']} | "
                f"source={description['skill_source'] or '-'} | "
                f"action={description['skill_action'] or '-'} | "
                f"status={description['skill_status'] or '-'}"
            ),
            (
                "Timing: "
                f"wake_ms={self._metric_text(description['wake_latency_ms'])} | "
                f"stt_ms={self._metric_text(description['stt_latency_ms'])} | "
                f"route_to_first_audio_ms={self._metric_text(description['route_to_first_audio_ms'])} | "
                f"response_first_audio_ms={self._metric_text(description['response_first_audio_ms'])} | "
                f"total_turn_ms={self._metric_text(description['total_turn_ms'])}"
            ),
            f"Voice reasons: {_fmt_list(description['voice_reasons'])}",
            f"Skill reasons: {_fmt_list(description['skill_reasons'])}",
            f"LLM reasons: {_fmt_list(description['llm_reasons'])}",
        ]
        return "\n".join(lines)

    def _voice_reasons(self, sample: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        for key in ("input_source", "stt_input_source", "wake_input_source"):
            value = str(sample.get(key, "") or "").strip().lower()
            if value == "voice":
                reasons.append(f"{key}=voice")
        return reasons

    def _llm_reasons(self, sample: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        llm_sources = getattr(self.validation_service, "_LLM_SOURCES", set())

        reply_source = str(sample.get("response_reply_source", "") or "").strip().lower()
        response_source = str(sample.get("response_source", "") or "").strip().lower()
        dialogue_source = str(sample.get("dialogue_source", "") or "").strip().lower()
        llm_source = str(sample.get("llm_source", "") or "").strip().lower()
        llm_first_chunk_ms = sample.get("llm_first_chunk_ms")

        if reply_source in llm_sources:
            reasons.append(f"response_reply_source={reply_source}")
        if response_source in llm_sources:
            reasons.append(f"response_source={response_source}")
        if dialogue_source in llm_sources:
            reasons.append(f"dialogue_source={dialogue_source}")
        if llm_source in llm_sources:
            reasons.append(f"llm_source={llm_source}")
        if llm_first_chunk_ms not in (None, 0, 0.0, ""):
            reasons.append(f"llm_first_chunk_ms={self._metric_text(llm_first_chunk_ms)}")

        return reasons

    def _skill_reasons(
        self,
        sample: dict[str, Any],
        *,
        llm_reasons: list[str],
    ) -> list[str]:
        reasons: list[str] = []

        if llm_reasons:
            reasons.append("excluded_because_llm=true")
            return reasons

        if bool(sample.get("skill_handled", False)):
            reasons.append("skill_handled=true")

        response_source = str(sample.get("response_source", "") or "").strip().lower()
        if response_source.startswith("action"):
            reasons.append(f"response_source={response_source}")
        if response_source.startswith("pending_"):
            reasons.append(f"response_source={response_source}")

        reply_source = str(sample.get("response_reply_source", "") or "").strip().lower()
        if reply_source in {"skill", "action", "builtin"}:
            reasons.append(f"response_reply_source={reply_source}")

        return reasons

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    @staticmethod
    def _metric_text(value: Any) -> str:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return "-"
        return f"{parsed:.1f}"


__all__ = ["TurnBenchmarkSampleDiagnosticsService"]