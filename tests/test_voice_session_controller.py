from __future__ import annotations

import unittest

from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_ASSISTANT_OUTPUT,
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_PHASE_COMMAND,
    VOICE_PHASE_SPEAK,
    VOICE_PHASE_WAKE_ACK,
    VOICE_STATE_LISTENING,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_WAKE_DETECTED,
    VoiceSessionController,
)


class VoiceSessionControllerTests(unittest.TestCase):
    def test_wake_transition_sets_phase_and_input_owner(self) -> None:
        controller = VoiceSessionController(wake_phrases=("nexa",))

        controller.transition_to_wake_detected(detail="wake_detected_test")
        snapshot = controller.snapshot()

        self.assertEqual(snapshot.state, VOICE_STATE_WAKE_DETECTED)
        self.assertEqual(snapshot.interaction_phase, VOICE_PHASE_WAKE_ACK)
        self.assertEqual(snapshot.input_owner, VOICE_INPUT_OWNER_ASSISTANT_OUTPUT)
        self.assertEqual(snapshot.detail, "wake_detected_test")
        self.assertGreater(snapshot.last_wake_detected_monotonic, 0.0)

    def test_active_window_and_response_finish_return_to_expected_state(self) -> None:
        controller = VoiceSessionController(active_listen_window_seconds=4.0)

        controller.open_active_window(
            seconds=3.0,
            phase=VOICE_PHASE_COMMAND,
            input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
            detail="awaiting_command",
        )
        listening_snapshot = controller.snapshot()
        self.assertEqual(listening_snapshot.state, VOICE_STATE_LISTENING)
        self.assertTrue(listening_snapshot.active_window_open)
        self.assertEqual(listening_snapshot.input_owner, VOICE_INPUT_OWNER_VOICE_INPUT)

        controller.transition_to_speaking(detail="response", phase=VOICE_PHASE_SPEAK)
        speaking_snapshot = controller.snapshot()
        self.assertEqual(speaking_snapshot.state, VOICE_STATE_SPEAKING)
        self.assertEqual(speaking_snapshot.input_owner, VOICE_INPUT_OWNER_ASSISTANT_OUTPUT)

        controller.mark_response_finished(detail="complete")
        finished_snapshot = controller.snapshot()
        self.assertEqual(finished_snapshot.state, VOICE_STATE_STANDBY)
        self.assertEqual(finished_snapshot.input_owner, VOICE_INPUT_OWNER_NONE)
        self.assertEqual(finished_snapshot.detail, "complete")

        controller.transition_to_standby(close_active_window=True)
        standby_snapshot = controller.snapshot()
        self.assertEqual(standby_snapshot.input_owner, VOICE_INPUT_OWNER_WAKE_GATE)
        self.assertFalse(standby_snapshot.active_window_open)

    def test_wake_and_cancel_matching_cover_aliases(self) -> None:
        controller = VoiceSessionController(wake_phrases=("nexa",))

        self.assertTrue(controller.heard_wake_phrase("hey nexa"))
        self.assertTrue(controller.heard_wake_phrase("nexta"))
        self.assertEqual(controller.strip_wake_phrase("nexa what time is it"), "what time is it")
        self.assertTrue(controller.looks_like_cancel_request("anuluj to"))


if __name__ == "__main__":
    unittest.main()