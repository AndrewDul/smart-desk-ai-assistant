from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.system.deployment import SystemdDeploymentService


class TestSystemdDeploymentService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

        (self.project_root / "main.py").write_text(
            "print(\"boot\")\n",
            encoding="utf-8",
        )

        python_bin_dir = self.project_root / ".venv" / "bin"
        python_bin_dir.mkdir(parents=True, exist_ok=True)
        (python_bin_dir / "python").write_text(
            "#!/usr/bin/env python3\n",
            encoding="utf-8",
        )

        self.output_dir = self.project_root / "generated-units"
        self.env_file = self.project_root / "config" / "systemd" / "nexa.env"
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        self.env_file.write_text("NEXA_LOG_LEVEL=INFO\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _base_settings(self) -> dict:
        return {
            "deployment": {
                "unit_output_dir": "generated-units",
                "app_unit_name": "nexa.service",
                "llm_unit_name": "nexa-llm.service",
                "user": "",
                "group": "",
                "python_path": ".venv/bin/python",
                "environment_file": "config/systemd/nexa.env",
                "app_restart": "on-failure",
                "app_restart_sec": 2.0,
                "app_start_limit_interval_sec": 30,
                "app_start_limit_burst": 5,
                "app_timeout_stop_sec": 25.0,
                "app_kill_signal": "SIGINT",
                "app_environment": {
                    "NEXA_PROFILE": "prod",
                },
                "llm_service_enabled": False,
                "llm_service_command": [],
                "llm_service_working_directory": "",
                "llm_restart": "on-failure",
                "llm_restart_sec": 2.0,
                "llm_start_limit_interval_sec": 30,
                "llm_start_limit_burst": 5,
                "llm_timeout_stop_sec": 20.0,
                "llm_kill_signal": "SIGTERM",
                "llm_environment": {},
            }
        }

    def test_render_units_resolves_paths_relative_to_service_project_root(self) -> None:
        settings = self._base_settings()
        service = SystemdDeploymentService(settings=settings)
        service.project_root = self.project_root

        with patch("modules.system.deployment.service.getpass.getuser", return_value="tester"):
            result = service.render_units()

        self.assertEqual(result.output_dir, str(self.output_dir.resolve()))
        self.assertIn("nexa.service", result.rendered_units)

        unit_text = result.rendered_units["nexa.service"]
        self.assertIn(f"WorkingDirectory={self.project_root}", unit_text)
        self.assertIn(
            f"ExecStart={self.project_root / '.venv/bin/python'} {self.project_root / 'main.py'}",
            unit_text,
        )
        self.assertIn(f"EnvironmentFile=-{self.env_file}", unit_text)
        self.assertIn("Environment=NEXA_PROFILE=prod", unit_text)
        self.assertIn("User=tester", unit_text)
        self.assertIn("Group=tester", unit_text)
        self.assertFalse(result.llm_unit_enabled)

    def test_render_units_adds_optional_llm_unit_and_dependency_order(self) -> None:
        settings = self._base_settings()
        settings["deployment"].update(
            {
                "llm_service_enabled": True,
                "llm_service_command": ["/usr/bin/env", "python3", "-m", "llm.server"],
                "llm_service_working_directory": "llm-runtime",
                "llm_environment": {"LLM_RUNNER": "hailo"},
            }
        )

        (self.project_root / "llm-runtime").mkdir(parents=True, exist_ok=True)

        service = SystemdDeploymentService(settings=settings)
        service.project_root = self.project_root

        with patch("modules.system.deployment.service.getpass.getuser", return_value="tester"):
            result = service.render_units()

        self.assertTrue(result.llm_unit_enabled)
        self.assertEqual(set(result.rendered_units), {"nexa.service", "nexa-llm.service"})

        app_text = result.rendered_units["nexa.service"]
        llm_text = result.rendered_units["nexa-llm.service"]

        self.assertIn("After=network-online.target sound.target nexa-llm.service", app_text)
        self.assertIn("Wants=network-online.target sound.target nexa-llm.service", app_text)
        self.assertIn(f"WorkingDirectory={self.project_root / 'llm-runtime'}", llm_text)
        self.assertIn("ExecStart=/usr/bin/env python3 -m llm.server", llm_text)
        self.assertIn("Environment=LLM_RUNNER=hailo", llm_text)

        ordered = service._ordered_unit_names(result)
        self.assertEqual(ordered[:2], ["nexa-llm.service", "nexa.service"])

    def test_install_units_copies_units_and_calls_systemctl_in_expected_order(self) -> None:
        settings = self._base_settings()
        service = SystemdDeploymentService(settings=settings)
        service.project_root = self.project_root
        install_dir = self.project_root / "etc-systemd"

        calls: list[list[str]] = []

        def capture_systemctl(args: list[str]) -> None:
            calls.append(list(args))

        with patch("modules.system.deployment.service.getpass.getuser", return_value="tester"):
            with patch.object(SystemdDeploymentService, "_systemctl", side_effect=capture_systemctl):
                result = service.install_units(
                    system_dir=str(install_dir),
                    enable=True,
                    start=True,
                )

        installed_path = install_dir / "nexa.service"
        self.assertTrue(installed_path.exists())
        self.assertEqual(
            installed_path.read_text(encoding="utf-8"),
            result.rendered_units["nexa.service"],
        )
        self.assertEqual(
            calls,
            [
                ["daemon-reload"],
                ["enable", "nexa.service"],
                ["restart", "nexa.service"],
            ],
        )


if __name__ == "__main__":
    unittest.main()