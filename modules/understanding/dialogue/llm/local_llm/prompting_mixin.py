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

            recent_context = str(
                context.get(
                    "recent_context",
                    user_profile.get("recent_conversation_context", ""),
                )
                or ""
            ).strip()

            return LocalLLMContext(
                user_name=str(user_profile.get("name", "") or context.get("user_name", "")),
                assistant_name=str(user_profile.get("assistant_name", "NeXa") or "NeXa"),
                conversation_topics=list(
                    context.get("topics", context.get("conversation_topics", [])) or []
                ),
                suggested_actions=list(context.get("suggested_actions", []) or []),
                user_text=user_text,
                route_kind=str(context.get("route_kind", "conversation") or "conversation"),
                recent_context=recent_context,
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
        max_sentences = 2
        style_hint = "concise_natural"

        support_topics = {
            "low_energy",
            "focus_struggle",
            "overwhelmed",
            "encouragement",
            "small_talk",
        }

        if topics & support_topics:
            n_predict = min(n_predict, 64)
            timeout_seconds = min(timeout_seconds, 8.5)
            temperature = min(temperature, 0.52)
            top_p = min(top_p, 0.88)
            max_sentences = 2
            style_hint = "warm_supportive"

        if "knowledge_query" in topics:
            n_predict = min(max(n_predict, 72), 96)
            timeout_seconds = min(max(timeout_seconds, 7.0), 10.0)
            temperature = min(temperature, 0.32)
            top_p = min(top_p, 0.82)
            max_sentences = 2
            style_hint = "clear_explainer"

        if "humour" in topics or "riddle" in topics or "interesting_fact" in topics:
            n_predict = min(n_predict, 60)
            timeout_seconds = min(timeout_seconds, 7.5)
            temperature = min(max(temperature, 0.50), 0.62)
            max_sentences = 2
            style_hint = "playful_brief"

        if route_kind == "unclear":
            n_predict = min(n_predict, 44)
            timeout_seconds = min(timeout_seconds, 7.0)
            temperature = min(temperature, 0.36)
            max_sentences = 1
            style_hint = "clarify_only"

        if route_kind == "mixed":
            n_predict = min(n_predict, 72)
            timeout_seconds = min(timeout_seconds, 8.5)
            temperature = min(temperature, 0.48)
            max_sentences = 2
            style_hint = "practical_bridge"

        if prompt_length > 900:
            prompt_chars = min(prompt_chars, 1500)
            n_predict = min(n_predict, 88)

        if self.runner in self._SERVER_RUNNERS:
            timeout_seconds = max(timeout_seconds, 6.0)

        return LocalLLMProfile(
            prompt_chars=max(320, int(prompt_chars)),
            n_predict=max(24, int(n_predict)),
            timeout_seconds=max(4.0, float(timeout_seconds)),
            temperature=max(0.1, float(temperature)),
            top_p=max(0.1, float(top_p)),
            top_k=max(1, int(top_k)),
            repeat_penalty=max(1.0, float(repeat_penalty)),
            max_sentences=max(1, int(max_sentences)),
            style_hint=style_hint,
        )

    def _build_hailo_compact_system_prompt(
        self,
        *,
        language: str,
        context: LocalLLMContext,
        profile: LocalLLMProfile,
    ) -> str:
        assistant_name = context.assistant_name or "NeXa"
        user_name = context.user_name or ""
        recent_context = self._compact_whitespace(str(context.recent_context or ""))
        topics = ", ".join(context.conversation_topics[:4]) if context.conversation_topics else ""
        style_hint = profile.style_hint

        if language == "pl":
            parts = [
                f"Jesteś {assistant_name}, lokalnym asystentem biurkowym.",
                "Odpowiadaj tylko po polsku.",
                f"Maksymalnie {profile.max_sentences} krótkie zdania.",
                "Odpowiadaj rzeczowo, naturalnie i bez list.",
                "Przy pytaniach o wiedzę ogólną wyjaśniaj prosto i krótko.",
                f"Styl odpowiedzi: {style_hint}.",
            ]
            if user_name:
                parts.append(f"Użytkownik ma na imię {user_name}.")
            if topics:
                parts.append(f"Tematy rozmowy: {topics}.")
            if recent_context:
                parts.append(f"Ostatni kontekst: {recent_context}.")
            parts.append("Zwróć wyłącznie końcową odpowiedź dla użytkownika.")
            return " ".join(part.strip() for part in parts if str(part).strip())

        parts = [
            f"You are {assistant_name}, a local desk assistant.",
            "Reply only in English.",
            f"Use at most {profile.max_sentences} short sentences.",
            "Be factual, natural, and concise.",
            "For general knowledge questions, explain simply and avoid speculation.",
            f"Reply style: {style_hint}.",
        ]
        if user_name:
            parts.append(f"The user's name is {user_name}.")
        if topics:
            parts.append(f"Current topics: {topics}.")
        if recent_context:
            parts.append(f"Recent context: {recent_context}.")
        parts.append("Return only the final user-facing answer.")
        return " ".join(part.strip() for part in parts if str(part).strip())


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
        
        if getattr(self, "runner", "") == "hailo-ollama":
            return self._build_hailo_compact_system_prompt(
                language=language,
                context=context,
                profile=profile,
            )
        if language == "pl":
            lines = [
                f"Jesteś {assistant_name}, lokalnym asystentem biurkowym.",
                "Odpowiadaj tylko po polsku.",
                "Nigdy nie mieszaj polskiego i angielskiego w jednej odpowiedzi, chyba że użytkownik wyraźnie tego chce.",
                "Brzmij naturalnie, krótko, spokojnie i pomocnie.",
                "Domyślnie odpowiadaj w 1-2 zdaniach.",
                f"Maksymalnie {profile.max_sentences} zdania.",
                "Nie opisuj swojego toku rozumowania.",
                "Nie używaj list ani punktów, jeśli użytkownik o to nie prosi.",
                "Nie twórz długich wstępów ani zakończeń.",
                "Nie brzmisz jak dokumentacja ani chatbot z szablonu.",
                "Jeśli użytkownik mówi o zmęczeniu, stresie, zagubieniu albo braku motywacji, najpierw okaż krótkie wsparcie, a potem zadaj jedno krótkie pytanie pomocnicze.",
                "Jeśli użytkownik zadaje pytanie o wiedzę ogólną, odpowiedz jasno i krótko. Gdy temat jest większy, podaj zwięzłą odpowiedź zamiast długiego wykładu.",
                "Jeśli nie masz pewności, powiedz to uczciwie krótko.",
                "Nie wymyślaj funkcji urządzenia, plików ani wykonanych działań.",
                "Jeśli coś wygląda na komendę, ale nie możesz wykonać akcji samą odpowiedzią, nie udawaj wykonania.",
                "Jeśli pytanie jest niejasne, zadaj tylko jedno krótkie pytanie doprecyzowujące.",
                f"Styl odpowiedzi: {style_hint}.",
            ]

            if user_name:
                lines.append(f"Użytkownik ma na imię {user_name}.")
            if topics:
                lines.append(f"Aktualne tematy rozmowy: {topics}.")
            if suggested_actions:
                lines.append(f"Możliwe działania w tle: {suggested_actions}.")
            if recent_context:
                lines.append(f"Ostatni kontekst rozmowy:\n{recent_context}")

            lines.append("Zwróć wyłącznie końcową odpowiedź dla użytkownika.")
            return "\n".join(lines)

        lines = [
            f"You are {assistant_name}, a local desk assistant.",
            "Reply only in English.",
            "Never mix English and Polish in one reply unless the user clearly asks for it.",
            "Sound natural, calm, concise, and helpful.",
            "Default to 1-2 sentences.",
            f"Use at most {profile.max_sentences} sentences.",
            "Do not reveal hidden reasoning.",
            "Do not use lists unless the user explicitly asks for them.",
            "Do not write long intros or long wrap-ups.",
            "Do not sound like documentation or a rigid scripted bot.",
            "If the user sounds tired, stressed, overwhelmed, or unsure, first give brief support and then ask one short helpful follow-up question.",
            "If the user asks a general knowledge question, answer clearly and briefly. Prefer a compact explanation over a long lecture.",
            "If you are uncertain, say so briefly and honestly.",
            "Do not invent device capabilities, file changes, or completed actions.",
            "If something looks like a command but cannot be executed by a text reply alone, do not pretend it was done.",
            "If the request is unclear, ask only one short clarification question.",
            f"Reply style: {style_hint}.",
        ]

        if user_name:
            lines.append(f"The user's name is {user_name}.")
        if topics:
            lines.append(f"Current conversation topics: {topics}.")
        if suggested_actions:
            lines.append(f"Possible background actions: {suggested_actions}.")
        if recent_context:
            lines.append(f"Recent conversation context:\n{recent_context}")

        lines.append("Return only the final user-facing answer.")
        return "\n".join(lines)