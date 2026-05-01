from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.core.flows.action_flow.executors.memory_executor import MemorySkillExecutor
from modules.core.flows.action_flow.memory_actions_mixin import ActionMemoryActionsMixin
from modules.core.flows.pending_flow.follow_up_mixin import PendingFlowFollowUpMixin
from modules.devices.audio.command_asr import CommandLanguage
from modules.features.memory.service import MemoryService
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime
from modules.shared.persistence.repositories import MemoryRepository


class Assistant:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self.pending_follow_up = None
        self.responses: list[dict] = []
        self.committed_language = ""

    def _localized(self, language: str, polish_text: str, english_text: str) -> str:
        return polish_text if str(language).lower().startswith("pl") else english_text

    def _commit_language(self, language: str) -> None:
        self.committed_language = str(language or "").strip().lower()

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind,
        source: str,
        metadata: dict | None = None,
    ) -> bool:
        self.responses.append(
            {
                "text": text,
                "language": language,
                "route_kind": str(route_kind),
                "source": source,
                "metadata": dict(metadata or {}),
            }
        )
        return True


class PendingFlow(PendingFlowFollowUpMixin):
    def __init__(self, assistant: Assistant) -> None:
        self.assistant = assistant

    def _follow_up_language(self, command_lang: str) -> str:
        follow_up = self.assistant.pending_follow_up or {}
        return str(follow_up.get("language", "") or command_lang or "en")

    def _is_no(self, text: str) -> bool:
        return str(text or "").strip().lower() in {"no", "nie"}


class MemoryActionFlow(ActionMemoryActionsMixin):
    def __init__(self, assistant: Assistant) -> None:
        self.assistant = assistant

    @staticmethod
    def _first_present(payload: dict, *names: str):
        for name in names:
            value = payload.get(name)
            if str(value or "").strip():
                return value
        return None

    @staticmethod
    def _resolve_memory_store_fields(payload: dict):
        return payload.get("key"), payload.get("value")

    def _get_memory_skill_executor(self) -> MemorySkillExecutor:
        return MemorySkillExecutor(assistant=self.assistant)

    def _deliver_feature_unavailable(self, *, language: str, action: str) -> bool:
        del language, action
        return False


def build_runtime():
    return build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "runtime_candidates_enabled": True,
                "runtime_candidate_intent_allowlist": [
                    "memory.guided_start",
                    "memory.list",
                    "assistant.identity",
                    "system.current_time",
                ],
            }
        }
    )


def assert_runtime_candidate(
    *,
    transcript: str,
    language_hint: CommandLanguage,
    expected_intent: str,
    expected_primary: str,
    expected_tool: str,
) -> dict:
    bundle = build_runtime()

    started = time.perf_counter()
    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id=f"manual-{expected_intent.replace('.', '-')}",
        transcript=transcript,
        language_hint=language_hint,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0

    route = result.route_decision
    tool_name = route.tool_invocations[0].tool_name if route and route.tool_invocations else ""

    assert result.accepted is True, result
    assert result.reason == "accepted", result.reason
    assert result.intent_key == expected_intent, result.intent_key
    assert route is not None
    assert route.primary_intent == expected_primary, route.primary_intent
    assert tool_name == expected_tool, tool_name
    assert route.metadata["voice_engine_intent_key"] == expected_intent
    assert route.metadata["tool_name"] == expected_tool
    assert route.metadata["llm_prevented"] is True

    return {
        "transcript": transcript,
        "accepted": result.accepted,
        "reason": result.reason,
        "intent_key": result.intent_key,
        "primary_intent": route.primary_intent,
        "tool_name": tool_name,
        "duration_ms": round(duration_ms, 3),
        "candidate_source": result.metadata.get("candidate_source", ""),
        "route_metadata_intent": route.metadata.get("voice_engine_intent_key", ""),
    }


def assert_guided_memory_flow(
    *,
    language: str,
    start_command: str,
    memory_text: str,
    recall_query: str,
    expected_recall: str,
) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_path = Path(temp_dir) / "memory.json"
        memory = MemoryService(store=MemoryRepository(path=str(memory_path)))
        assistant = Assistant(memory)

        started = time.perf_counter()

        action_flow = MemoryActionFlow(assistant)
        handled = action_flow._handle_memory_store(
            route=SimpleNamespace(),
            language=language,
            payload={"guided": True},
            resolved=SimpleNamespace(source="manual_check"),
        )

        assert handled is True
        assert assistant.pending_follow_up == {
            "type": "memory_message",
            "language": language,
        }

        pending_flow = PendingFlow(assistant)
        decision = pending_flow.handle_pending_follow_up(memory_text, language)

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_message"
        assert assistant.pending_follow_up is None

        recalled = memory.recall(recall_query, language=language)
        assert recalled == expected_recall, recalled

        list_outcome = MemorySkillExecutor(assistant=assistant).list_items()
        assert list_outcome.ok is True
        assert expected_recall in list(list_outcome.data["items"].values())

        duration_ms = (time.perf_counter() - started) * 1000.0

        return {
            "start_command": start_command,
            "memory_text": memory_text,
            "recall_query": recall_query,
            "recalled": recalled,
            "language": language,
            "duration_ms": round(duration_ms, 3),
            "records": [item["original_text"] for item in memory.list_records(language=language)],
            "last_response": assistant.responses[-1],
        }


def main() -> None:
    results = {
        "runtime_candidates": [
            assert_runtime_candidate(
                transcript="remember something",
                language_hint=CommandLanguage.ENGLISH,
                expected_intent="memory.guided_start",
                expected_primary="memory_store",
                expected_tool="memory.guided_start",
            ),
            assert_runtime_candidate(
                transcript="what do you remember",
                language_hint=CommandLanguage.ENGLISH,
                expected_intent="memory.list",
                expected_primary="memory_list",
                expected_tool="memory.list",
            ),
            assert_runtime_candidate(
                transcript="zapamiętaj coś",
                language_hint=CommandLanguage.POLISH,
                expected_intent="memory.guided_start",
                expected_primary="memory_store",
                expected_tool="memory.guided_start",
            ),
            assert_runtime_candidate(
                transcript="co zapamiętałaś",
                language_hint=CommandLanguage.POLISH,
                expected_intent="memory.list",
                expected_primary="memory_list",
                expected_tool="memory.list",
            ),
        ],
        "guided_memory": [
            assert_guided_memory_flow(
                language="pl",
                start_command="zapamiętaj coś",
                memory_text="klucze są w kuchni",
                recall_query="przypomnij mi gdzie są klucze",
                expected_recall="klucze są w kuchni",
            ),
            assert_guided_memory_flow(
                language="en",
                start_command="remember something",
                memory_text="my phone is on the desk",
                recall_query="where is my phone",
                expected_recall="my phone is on the desk",
            ),
        ],
    }

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("GUIDED_MEMORY_RUNTIME_CHECK_OK")


if __name__ == "__main__":
    main()
