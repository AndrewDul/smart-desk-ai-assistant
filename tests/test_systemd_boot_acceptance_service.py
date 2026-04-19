from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.system.deployment.acceptance import SystemdBootAcceptanceService


class TestSystemdBootAcceptanceService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.system_dir = self.project_root / "etc-systemd"
        self.system_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _base_settings(self) -> dict:
        return {
            "deployment": {
                "app_unit_name": "nexa.service",
                "llm_unit_name": "nexa-llm.service",
                "llm_service_enabled": False,
            },
            "runtime_product": {
                "status_path": "var/data/runtime_status.json",
            },
        }

    def _write_runtime_status(
        self,
        *,
        lifecycle_state: str,
        startup_mode: str,
        primary_ready: bool,
        premium_ready: bool,
    ) -> None:
        runtime_path = self.project_root / "var" / "data" / "runtime_status.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(
            (
                "{"
                f"\"lifecycle_state\": \"{lifecycle_state}\", "
                f"\"startup_mode\": \"{startup_mode}\", "
                f"\"primary_ready\": {str(primary_ready).lower()}, "
                f"\"premium_ready\": {str(premium_ready).lower()}"
                "}"
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _completed(
        args: list[str],
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_acceptance_passes_for_premium_ready_boot(self) -> None:
        settings = self._base_settings()
        service = SystemdBootAcceptanceService(settings=settings)
        service.project_root = self.project_root

        (self.system_dir / "nexa.service").write_text("UNIT\n", encoding="utf-8")
        self._write_runtime_status(
            lifecycle_state="ready",
            startup_mode="premium",
            primary_ready=True,
            premium_ready=True,
        )

        def fake_run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["systemctl", "show", "nexa.service"]:
                return self._completed(
                    args,
                    stdout=(
                        "ActiveState=active\n"
                        "SubState=running\n"
                        "UnitFileState=enabled\n"
                        "FragmentPath=/etc/systemd/system/nexa.service\n"
                    ),
                )
            if args[:2] == ["journalctl", "-u"]:
                return self._completed(args, stdout="nexa journal line\n")
            raise AssertionError(f"Unexpected command: {args}")

        with patch.object(service, "_run_command", side_effect=fake_run_command):
            result = service.run(
                system_dir=str(self.system_dir),
                allow_degraded=False,
                include_journal=True,
                journal_lines=20,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.checked_unit_names, ["nexa.service"])
        self.assertIn("nexa.service", result.unit_states)
        self.assertIn("nexa.service", result.journal_tails)
        self.assertEqual(result.failed_checks(), [])

    def test_acceptance_fails_in_strict_mode_for_degraded_runtime(self) -> None:
        settings = self._base_settings()
        service = SystemdBootAcceptanceService(settings=settings)
        service.project_root = self.project_root

        (self.system_dir / "nexa.service").write_text("UNIT\n", encoding="utf-8")
        self._write_runtime_status(
            lifecycle_state="degraded",
            startup_mode="limited",
            primary_ready=True,
            premium_ready=False,
        )

        def fake_run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["systemctl", "show", "nexa.service"]:
                return self._completed(
                    args,
                    stdout=(
                        "ActiveState=active\n"
                        "SubState=running\n"
                        "UnitFileState=enabled\n"
                    ),
                )
            raise AssertionError(f"Unexpected command: {args}")

        with patch.object(service, "_run_command", side_effect=fake_run_command):
            result = service.run(
                system_dir=str(self.system_dir),
                allow_degraded=False,
                include_journal=False,
            )

        self.assertFalse(result.ok)
        failed_keys = [item.key for item in result.failed_checks()]
        self.assertIn("runtime-product-state", failed_keys)

    def test_acceptance_allows_degraded_mode_when_explicitly_enabled(self) -> None:
        settings = self._base_settings()
        service = SystemdBootAcceptanceService(settings=settings)
        service.project_root = self.project_root

        (self.system_dir / "nexa.service").write_text("UNIT\n", encoding="utf-8")
        self._write_runtime_status(
            lifecycle_state="degraded",
            startup_mode="limited",
            primary_ready=True,
            premium_ready=False,
        )

        def fake_run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["systemctl", "show", "nexa.service"]:
                return self._completed(
                    args,
                    stdout=(
                        "ActiveState=active\n"
                        "SubState=running\n"
                        "UnitFileState=enabled\n"
                    ),
                )
            raise AssertionError(f"Unexpected command: {args}")

        with patch.object(service, "_run_command", side_effect=fake_run_command):
            result = service.run(
                system_dir=str(self.system_dir),
                allow_degraded=True,
                include_journal=False,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.failed_checks(), [])


if __name__ == "__main__":
    unittest.main()