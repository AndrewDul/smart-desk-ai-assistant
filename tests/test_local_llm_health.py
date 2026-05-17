from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from modules.understanding.dialogue.llm.local_llm import LocalLLMService


class LocalLLMHealthTests(unittest.TestCase):
    def _build_service(self) -> LocalLLMService:
        return LocalLLMService(
            {
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                    "server_url": "http://127.0.0.1:8000",
                    "startup_warmup": True,
                    "auto_recovery_enabled": True,
                    "auto_recovery_cooldown_seconds": 0.0,
                    "max_auto_recovery_attempts": 2,
                }
            }
        )

    def test_backend_health_snapshot_reports_degraded_when_server_is_available_but_not_warmed(self) -> None:
        service = self._build_service()
        service._record_backend_availability_result(True, error="")
        service._last_warmup_ok = False

        snapshot = service.backend_health_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["state"], "degraded")
        self.assertTrue(snapshot["warmup_required"])
        self.assertFalse(snapshot["warmup_ready"])
        self.assertIn("warmup", snapshot["capabilities"])

    def test_ensure_backend_ready_attempts_auto_recovery_and_returns_ready_snapshot(self) -> None:
        service = self._build_service()
        state = {"available": False}

        def fake_is_available() -> bool:
            service._record_backend_availability_result(
                state["available"],
                error="" if state["available"] else "server down",
            )
            return state["available"]

        def fake_warmup() -> bool:
            state["available"] = True
            service._record_warmup_result(ok=True, error="")
            service._record_backend_availability_result(True, error="")
            return True

        with mock.patch.object(service, "is_available", side_effect=fake_is_available):
            with mock.patch.object(service, "warmup_backend_if_enabled", side_effect=fake_warmup):
                snapshot = service.ensure_backend_ready(auto_recover=True)

        self.assertTrue(snapshot["recovery_attempted"])
        self.assertTrue(snapshot["recovery_ok"])
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["state"], "ready")

    def test_cached_backend_readiness_uses_fresh_snapshot_without_probe(self) -> None:
        service = self._build_service()
        service._record_backend_availability_result(True, error="")
        service._record_warmup_result(ok=True, error="")

        with mock.patch.object(service, "is_available", side_effect=AssertionError("probe should not run")):
            snapshot = service.cached_backend_readiness(refresh_if_stale=False)

        self.assertTrue(snapshot["cache_hit"])
        self.assertFalse(snapshot["refreshed"])
        self.assertEqual(snapshot["state"], "ready")

    def test_cached_backend_readiness_can_refresh_stale_snapshot_when_requested(self) -> None:
        service = self._build_service()
        service._backend_last_checked_at = 1.0
        service._backend_available = False

        with mock.patch.object(service, "ensure_backend_ready", return_value={"state": "ready"}) as ensure:
            snapshot = service.cached_backend_readiness(
                max_age_seconds=0.25,
                refresh_if_stale=True,
            )

        ensure.assert_called_once_with(auto_recover=False)
        self.assertTrue(snapshot["refreshed"])
        self.assertEqual(snapshot["state"], "ready")

    def test_llama_server_missing_binary_reports_backend_missing(self) -> None:
        service = LocalLLMService(
            {
                "llm": {
                    "enabled": True,
                    "runner": "llama-server",
                    "command": "missing-llama-server",
                    "model_path": "models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
                    "startup_warmup": False,
                }
            }
        )

        snapshot = service.ensure_backend_ready(auto_recover=False)

        self.assertEqual(snapshot["state"], "backend_missing")
        self.assertEqual(snapshot["readiness_state"], "backend_missing")
        self.assertFalse(snapshot["available"])
        self.assertIn("llama-server backend command not found", snapshot["last_error"])

    def test_llama_server_missing_model_reports_model_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command_path = Path(temp_dir) / "llama-server"
            command_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command_path.chmod(0o755)

            service = LocalLLMService(
                {
                    "llm": {
                        "enabled": True,
                        "runner": "llama-server",
                        "command": str(command_path),
                        "model_path": str(Path(temp_dir) / "missing.gguf"),
                        "startup_warmup": False,
                    }
                }
            )

            snapshot = service.ensure_backend_ready(auto_recover=False)

        self.assertEqual(snapshot["state"], "model_missing")
        self.assertEqual(snapshot["readiness_state"], "model_missing")
        self.assertFalse(snapshot["available"])
        self.assertIn("LLM GGUF model file is missing", snapshot["last_error"])

    def test_llama_server_reachable_openai_models_reports_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command_path = Path(temp_dir) / "llama-server"
            command_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command_path.chmod(0o755)
            model_path = Path(temp_dir) / "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
            model_path.write_bytes(b"gguf")

            service = LocalLLMService(
                {
                    "llm": {
                        "enabled": True,
                        "runner": "llama-server",
                        "command": str(command_path),
                        "model_path": str(model_path),
                        "server_health_path": "/v1/models",
                        "server_chat_path": "/v1/chat/completions",
                        "server_model_name": "Qwen2.5-1.5B-Instruct-Q4_K_M",
                        "startup_warmup": False,
                    }
                }
            )

            class _Response:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self) -> bytes:
                    return b'{"data":[{"id":"Qwen2.5-1.5B-Instruct-Q4_K_M"}]}'

            with mock.patch.object(service, "_tcp_port_open", return_value=True):
                with mock.patch("urllib.request.urlopen", return_value=_Response()):
                    snapshot = service.ensure_backend_ready(auto_recover=False)

        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["readiness_state"], "ready")
        self.assertTrue(snapshot["available"])
        self.assertTrue(snapshot["healthy"])

    def test_llama_server_with_binary_and_model_but_closed_port_reports_starting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command_path = Path(temp_dir) / "llama-server"
            command_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command_path.chmod(0o755)
            model_path = Path(temp_dir) / "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
            model_path.write_bytes(b"gguf")

            service = LocalLLMService(
                {
                    "llm": {
                        "enabled": True,
                        "runner": "llama-server",
                        "command": str(command_path),
                        "model_path": str(model_path),
                        "startup_warmup": False,
                    }
                }
            )

            with mock.patch.object(service, "_tcp_port_open", return_value=False):
                snapshot = service.ensure_backend_ready(auto_recover=False)

        self.assertEqual(snapshot["state"], "starting")
        self.assertEqual(snapshot["readiness_state"], "starting")
        self.assertFalse(snapshot["available"])
        self.assertIn("server port is not reachable", snapshot["last_error"])

    def test_llama_server_uses_openai_compatible_chat_path(self) -> None:
        service = LocalLLMService(
            {
                "llm": {
                    "enabled": True,
                    "runner": "llama-server",
                    "server_url": "http://127.0.0.1:8000",
                    "model_path": "models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
                    "server_model_name": "Qwen2.5-1.5B-Instruct-Q4_K_M",
                }
            }
        )

        self.assertEqual(service.server_chat_path, "/v1/chat/completions")
        self.assertEqual(service.server_health_path, "/v1/models")
        self.assertTrue(service.server_use_openai_compat)

        profile = service._profile_class(
            prompt_chars=64,
            n_predict=16,
            timeout_seconds=2.0,
            temperature=0.2,
            top_p=0.9,
            top_k=20,
            repeat_penalty=1.0,
            max_sentences=1,
            style_hint="test",
        )
        candidates = service._server_request_candidates(
            base_url="http://127.0.0.1:8000",
            system_prompt="system",
            user_prompt="hello",
            profile=profile,
            stream=True,
        )

        self.assertEqual(candidates[0]["url"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertIn("max_tokens", candidates[0]["payload"])


if __name__ == "__main__":
    unittest.main()
