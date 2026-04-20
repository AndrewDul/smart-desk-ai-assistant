from __future__ import annotations

import unittest

from modules.runtime.contracts import RuntimeBackendStatus
from modules.runtime.product import RuntimeProductService


class _FakeLocalLlm:
    def describe_backend(self) -> dict[str, object]:
        return {
            "runner": "hailo-ollama",
            "capabilities": ["streaming", "healthcheck"],
        }

    def is_available(self) -> bool:
        return True

    def warmup_backend_if_enabled(self) -> bool:
        return True


class _FakeDialogue:
    def __init__(self) -> None:
        self.local_llm = _FakeLocalLlm()


class _FakeRuntime:
    def __init__(self) -> None:
        self.backend_statuses = {
            "voice_input": RuntimeBackendStatus(
                component="voice_input",
                ok=True,
                selected_backend="faster_whisper",
                requested_backend="faster_whisper",
                runtime_mode="speech_to_text",
                capabilities=("listen", "listen_once", "transcribe"),
            ),
            "wake_gate": RuntimeBackendStatus(
                component="wake_gate",
                ok=True,
                selected_backend="compatibility_voice_input",
                requested_backend="openwakeword",
                runtime_mode="single_capture_compatibility",
                capabilities=("listen_for_wake_phrase",),
                detail="Wake gate reuses the main voice input backend.",
            ),
            "voice_output": RuntimeBackendStatus(
                component="voice_output",
                ok=True,
                selected_backend="piper",
                requested_backend="piper",
                runtime_mode="speech_output",
                capabilities=("speak", "stop_playback"),
            ),
            "display": RuntimeBackendStatus(
                component="display",
                ok=True,
                selected_backend="waveshare_2inch",
                requested_backend="waveshare_2inch",
                runtime_mode="display_output",
                capabilities=("show_block", "show_status"),
            ),
        }


class RuntimeProductServiceTests(unittest.TestCase):
    def test_provider_inventory_marks_compatibility_path_and_blocks_only_premium_ready(self) -> None:
        service = RuntimeProductService(
            settings={
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                }
            },
            persist_enabled=False,
        )
        service.bind_runtime(runtime=_FakeRuntime(), dialogue=_FakeDialogue())

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertTrue(snapshot["startup_allowed"])
        self.assertTrue(snapshot["primary_ready"])
        self.assertFalse(snapshot["premium_ready"])
        self.assertEqual(snapshot["startup_mode"], "limited")
        self.assertIn("wake_gate", snapshot["compatibility_components"])
        self.assertIn("wake_gate: compatibility path active", snapshot["warnings"])
        self.assertEqual(
            snapshot["status_message"],
            "runtime ready with compatibility path: wake_gate",
        )

        provider_inventory = snapshot["provider_inventory"]
        self.assertIn("wake_gate", provider_inventory)

        wake_payload = provider_inventory["wake_gate"]
        self.assertEqual(wake_payload["requested_backend"], "openwakeword")
        self.assertEqual(wake_payload["selected_backend"], "compatibility_voice_input")
        self.assertEqual(wake_payload["runtime_mode"], "single_capture_compatibility")
        self.assertTrue(wake_payload["compatibility_mode"])
        self.assertFalse(wake_payload["primary"])

    def test_provider_inventory_is_premium_ready_when_all_required_services_are_primary(self) -> None:
        runtime = _FakeRuntime()
        runtime.backend_statuses["wake_gate"] = RuntimeBackendStatus(
            component="wake_gate",
            ok=True,
            selected_backend="openwakeword",
            requested_backend="openwakeword",
            runtime_mode="dedicated_wake_gate",
            capabilities=("listen_for_wake_phrase", "detect_wake"),
            detail="OpenWakeWord wake gate loaded successfully.",
        )

        service = RuntimeProductService(
            settings={
                "llm": {
                    "enabled": False,
                    "runner": "hailo-ollama",
                }
            },
            persist_enabled=False,
        )
        service.bind_runtime(runtime=runtime, dialogue=_FakeDialogue())

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertTrue(snapshot["primary_ready"])
        self.assertTrue(snapshot["premium_ready"])
        self.assertEqual(snapshot["compatibility_components"], [])
        self.assertEqual(
            snapshot["provider_inventory"]["wake_gate"]["selected_backend"],
            "openwakeword",
        )
        self.assertTrue(snapshot["provider_inventory"]["wake_gate"]["primary"])


if __name__ == "__main__":
    unittest.main()