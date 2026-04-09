from __future__ import annotations

from typing import Any

from .models import LocalLLMContext, LocalLLMProfile


class LocalLLMPromptingMixin:
    def _coerce_context(
        self,
        context: dict[str, Any] | LocalLLMContext | None,
        *,
        user_text: str,
    ) -> LocalLLMContext:
        if isinstance(context, LocalLLMContext):
            return context

        if isinstance(context, dict):
            user_profile = dict(context.get("user_profile", {}) or {})
            return LocalLLMContext(
                user_name=str(user_profile.get("name", "") or context.get("user_name", "")),
                assistant_name=str(user_profile.get("assistant_name", "NeXa") or "NeXa"),
                conversation_topics=list(
                    context.get("topics", context.get("conversation_topics", [])) or []
                ),
                suggested_actions=list(context.get("suggested_actions", []) or []),
                user_text=user_text,
                route_kind=str(context.get("route_kind", "conversation") or "conversation"),
                recent_context=str(context.get("recent_context", "") or ""),
                user_profile=user_profile,
            )

        return LocalLLMContext(user_text=user_text)

    def _build_generation_profile(
        self,
        *,
        language: str,
        context: LocalLLMContext,
        user_prompt: str,
    ) -> LocalLLMProfile:
        del language

        topics = set(context.conversation_topics)
        route_kind = str(context.route_kind or "conversation").strip().lower()
        prompt_length = len(str(user_prompt or ""))

        prompt_chars = self.max_prompt_chars
        n_predict = self.n_predict
        timeout_seconds = self.timeout_seconds
        temperature = self.temperature
        top_p = self.top_p
        top_k = self.top_k
        repeat_penalty = self.repeat_penalty
        max_sentences = 3
        style_hint = "balanced"

        support_topics = {"low_energy", "focus_struggle", "overwhelmed", "encouragement", "small_talk"}
        if topics & support_topics:
            n_predict = min(n_predict, 72)
            timeout_seconds = min(timeout_seconds, 10.0)
            temperature = min(temperature, 0.58)
            top_p = min(top_p, 0.9)
            max_sentences = 2
            style_hint = "warm_brief"

        if "knowledge_query" in topics:
            n_predict = max(n_predict, 112)
            timeout_seconds = max(timeout_seconds, 20.0)
            temperature = min(temperature, 0.55)
            max_sentences = 3
            style_hint = "direct_explainer"

        if route_kind == "unclear":
            n_predict = min(n_predict, 56)
            timeout_seconds = min(timeout_seconds, 8.5)
            temperature = min(temperature, 0.45)
            max_sentences = 2
            style_hint = "clarify_brief"

        if route_kind == "mixed":
            n_predict = min(n_predict, 80)
            timeout_seconds = min(timeout_seconds, 10.0)
            max_sentences = 2
            style_hint = "practical_bridge"

        if prompt_length > 900:
            prompt_chars = min(prompt_chars, 1400)
            n_predict = min(n_predict, 96)

        if self.runner in self._SERVER_RUNNERS:
            timeout_seconds = max(timeout_seconds, 6.0)

        return LocalLLMProfile(
            prompt_chars=max(300, int(prompt_chars)),
            n_predict=max(24, int(n_predict)),
            timeout_seconds=max(4.0, float(timeout_seconds)),
            temperature=max(0.1, float(temperature)),
            top_p=max(0.1, float(top_p)),
            top_k=max(1, int(top_k)),
            repeat_penalty=max(1.0, float(repeat_penalty)),
            max_sentences=max(1, int(max_sentences)),
            style_hint=style_hint,
        )

    def _build_system_prompt(
        self,
        *,
        language: str,
        context: LocalLLMContext,
        profile: LocalLLMProfile,
    ) -> str:
        assistant_name = context.assistant_name or "NeXa"
        user_name = context.user_name or ""
        recent_context = str(context.recent_context or "").strip()
        suggested_actions = ", ".join(context.suggested_actions[:4]) if context.suggested_actions else ""
        topics = ", ".join(context.conversation_topics[:6]) if context.conversation_topics else ""
        style_hint = profile.style_hint

        if language == "pl":
            lines = [
                f"Jesteś {assistant_name}, premium asystentem biurkowym działającym lokalnie.",
                "Odpowiadaj po polsku.",
                "Mów naturalnie, krótko i konkretnie.",
                "Nie opisuj swojego procesu myślenia.",
                "Nie wypisuj punktów, chyba że użytkownik wyraźnie o to prosi.",
                "Nie twórz długich wstępów ani zakończeń.",
                "Brzmij pomocnie, spokojnie i profesjonalnie.",
                "Jeżeli pytanie jest niejasne, poproś o doprecyzowanie w jednym krótkim zdaniu.",
                f"Styl odpowiedzi: {style_hint}.",
                f"Maksymalnie {profile.max_sentences} zdania.",
            ]
            if user_name:
                lines.append(f"Użytkownik ma na imię {user_name}.")
            if topics:
                lines.append(f"Tematy rozmowy: {topics}.")
            if suggested_actions:
                lines.append(f"Sugerowane działania: {suggested_actions}.")
            if recent_context:
                lines.append(f"Ostatni kontekst rozmowy: {recent_context}")
            lines.append("Zwróć wyłącznie końcową odpowiedź dla użytkownika.")
            return "\n".join(lines)

        lines = [
            f"You are {assistant_name}, a premium local desk assistant.",
            "Reply in English.",
            "Be natural, concise, and practical.",
            "Do not describe hidden reasoning.",
            "Avoid bullets unless the user explicitly asks for them.",
            "Do not produce long intros or long wrap-ups.",
            "Sound calm, helpful, and professional.",
            "If the request is unclear, ask for clarification in one short sentence.",
            f"Reply style: {style_hint}.",
            f"Use at most {profile.max_sentences} sentences.",
        ]
        if user_name:
            lines.append(f"The user's name is {user_name}.")
        if topics:
            lines.append(f"Conversation topics: {topics}.")
        if suggested_actions:
            lines.append(f"Suggested actions: {suggested_actions}.")
        if recent_context:
            lines.append(f"Recent conversation context: {recent_context}")
        lines.append("Return only the final user-facing answer.")
        return "\n".join(lines)