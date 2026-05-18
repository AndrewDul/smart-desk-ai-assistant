from __future__ import annotations

import unittest

from modules.understanding.dialogue.conversation_memory import ConversationMemory


class ConversationMemoryTests(unittest.TestCase):
    def test_action_response_does_not_leak_into_llm_prompt_context(self) -> None:
        memory = ConversationMemory(max_turns=8, max_total_chars=1800)

        memory.add_user_turn(
            "what time is it",
            language="en",
            metadata={"source": "voice"},
        )
        memory.add_assistant_turn(
            "21 44",
            language="en",
            metadata={
                "source": "action_flow:ask_time",
                "route_kind": "action",
            },
        )
        memory.add_user_turn(
            "Explain black holes in simple words.",
            language="en",
            metadata={"source": "voice"},
        )

        prompt_context = memory.summary_for_prompt(limit=6, preferred_language="en")

        self.assertNotIn("21 44", prompt_context)
        self.assertNotIn("Open thread: what time is it", prompt_context)
        self.assertIn("Explain black holes", prompt_context)


if __name__ == "__main__":
    unittest.main()
