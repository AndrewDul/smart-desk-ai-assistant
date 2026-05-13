#!/usr/bin/env python3
"""Repair NeXa real voice drive runtime launch path.

This script is intentionally small and idempotent. It does not change drive
movement logic. It only prevents confusing terminal Wake>/You> fallback during
voice-drive launches and adds a launcher that requires real microphone + wake
word backends.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"[REPAIR] wrote {path.relative_to(PROJECT_ROOT)}")


def _ensure_import_os(text: str) -> str:
    if "import os" in text:
        return text
    return text.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport os\n\n", 1)


def _insert_after_marker(text: str, marker: str, insertion: str) -> str:
    if insertion.strip() in text:
        return text
    if marker not in text:
        raise RuntimeError(f"Marker not found: {marker!r}")
    return text.replace(marker, marker + insertion, 1)


def _patch_voice_input_mixin() -> None:
    path = PROJECT_ROOT / "modules/runtime/builder/voice_input_mixin.py"
    text = _ensure_import_os(_read(path))

    strict_helpers = '''\n\ndef _strict_real_voice_input_required() -> bool:\n    return str(os.environ.get("NEXA_REQUIRE_REAL_VOICE_INPUT", "") or "").strip().lower() in {\n        "1",\n        "true",\n        "yes",\n        "on",\n        "run",\n    }\n\n\ndef _raise_if_strict_real_voice_input_required(detail: str) -> None:\n    if _strict_real_voice_input_required():\n        raise RuntimeError(\n            "Real voice input is required for this runtime, but NeXa would fall back "\n            f"to developer text input. {detail}"\n        )\n'''
    text = _insert_after_marker(text, "LOGGER = get_logger(__name__)\n", strict_helpers)

    disabled_pattern = '''        if not bool(config.get("enabled", True)):\n            backend = text_input_class()\n'''
    disabled_replacement = '''        if not bool(config.get("enabled", True)):\n            _raise_if_strict_real_voice_input_required(\n                "voice_input.enabled is false in config."\n            )\n            backend = text_input_class()\n'''
    text = text.replace(disabled_pattern, disabled_replacement, 1)

    unsupported_pattern = '''            backend = text_input_class()\n            return (\n                backend,\n                RuntimeBackendStatus(\n                    component="voice_input",\n                    ok=False,\n                    selected_backend="text_input",\n                    requested_backend=engine,\n                    runtime_mode="developer_text_input",\n                    capabilities=("text_input", "transcribe"),\n                    detail=f"Unsupported voice input engine '{engine}'. Using text input instead.",\n                    fallback_used=True,\n                ),\n            )\n\n        except Exception as error:\n'''
    unsupported_replacement = '''            _raise_if_strict_real_voice_input_required(\n                f"Unsupported voice input engine '{engine}'."\n            )\n            backend = text_input_class()\n            return (\n                backend,\n                RuntimeBackendStatus(\n                    component="voice_input",\n                    ok=False,\n                    selected_backend="text_input",\n                    requested_backend=engine,\n                    runtime_mode="developer_text_input",\n                    capabilities=("text_input", "transcribe"),\n                    detail=f"Unsupported voice input engine '{engine}'. Using text input instead.",\n                    fallback_used=True,\n                ),\n            )\n\n        except Exception as error:\n'''
    text = text.replace(unsupported_pattern, unsupported_replacement, 1)

    exception_anchor = '''            backend = text_input_class()\n            return (\n                backend,\n                RuntimeBackendStatus(\n                    component="voice_input",\n                    ok=False,\n                    selected_backend="text_input",\n                    requested_backend=engine,\n                    runtime_mode="developer_text_input",\n                    capabilities=("text_input", "transcribe"),\n                    detail=(\n                        f"Voice input backend '{engine}' failed. "\n'''
    exception_replacement = '''            _raise_if_strict_real_voice_input_required(\n                f"Voice input backend '{engine}' failed with {type(error).__name__}: {error}. "\n                f"Config: device_index={config.get('device_index')}, "\n                f"device_name_contains={config.get('device_name_contains')}, "\n                f"sample_rate={config.get('sample_rate')}"\n            )\n            backend = text_input_class()\n            return (\n                backend,\n                RuntimeBackendStatus(\n                    component="voice_input",\n                    ok=False,\n                    selected_backend="text_input",\n                    requested_backend=engine,\n                    runtime_mode="developer_text_input",\n                    capabilities=("text_input", "transcribe"),\n                    detail=(\n                        f"Voice input backend '{engine}' failed. "\n'''
    text = text.replace(exception_anchor, exception_replacement, 1)

    _write(path, text)


def _patch_wake_gate_mixin() -> None:
    path = PROJECT_ROOT / "modules/runtime/builder/wake_gate_mixin.py"
    text = _ensure_import_os(_read(path))

    strict_helpers = '''\n\ndef _strict_real_wake_gate_required() -> bool:\n    return str(os.environ.get("NEXA_REQUIRE_REAL_WAKE_GATE", "") or "").strip().lower() in {\n        "1",\n        "true",\n        "yes",\n        "on",\n        "run",\n    }\n\n\ndef _raise_if_strict_real_wake_gate_required(detail: str) -> None:\n    if _strict_real_wake_gate_required():\n        raise RuntimeError(\n            "A real wake-word gate is required for this runtime, but NeXa would use "\n            f"developer text/compatibility wake mode. {detail}"\n        )\n'''
    text = _insert_after_marker(text, "from .wake_gate import CompatibilityWakeGate\n", strict_helpers)

    replacements = [
        (
            '''            if "textinput" in class_name:\n                return (\n''',
            '''            if "textinput" in class_name:\n                _raise_if_strict_real_wake_gate_required(\n                    "voice_input selected the TextInput wake backend."\n                )\n                return (\n''',
        ),
        (
            '''        if not bool(config.get("enabled", True)):\n            return (\n''',
            '''        if not bool(config.get("enabled", True)):\n            _raise_if_strict_real_wake_gate_required(\n                "voice_input.enabled is false, so wake gate is disabled."\n            )\n            return (\n''',
        ),
        (
            '''        if engine in {"off", "none", "disabled"}:\n            return (\n''',
            '''        if engine in {"off", "none", "disabled"}:\n            _raise_if_strict_real_wake_gate_required(\n                f"wake_engine is '{engine}'."\n            )\n            return (\n''',
        ),
        (
            '''        if single_capture_mode and bool(voice_input_status.ok) and not prefer_dedicated_gate:\n            compatibility_gate = CompatibilityWakeGate(voice_input)\n''',
            '''        if single_capture_mode and bool(voice_input_status.ok) and not prefer_dedicated_gate:\n            _raise_if_strict_real_wake_gate_required(\n                "wake_prefer_dedicated_gate is false, so compatibility wake would be used."\n            )\n            compatibility_gate = CompatibilityWakeGate(voice_input)\n''',
        ),
        (
            '''            compatibility_gate = CompatibilityWakeGate(voice_input)\n            return (\n''',
            '''            _raise_if_strict_real_wake_gate_required(\n                f"Unsupported wake engine '{engine}'."\n            )\n            compatibility_gate = CompatibilityWakeGate(voice_input)\n            return (\n''',
        ),
        (
            '''            if bool(voice_input_status.ok):\n                compatibility_gate = CompatibilityWakeGate(voice_input)\n                return (\n''',
            '''            if bool(voice_input_status.ok):\n                _raise_if_strict_real_wake_gate_required(\n                    f"Wake gate backend '{engine}' failed: {error}"\n                )\n                compatibility_gate = CompatibilityWakeGate(voice_input)\n                return (\n''',
        ),
    ]
    for old, new in replacements:
        text = text.replace(old, new, 1)

    _write(path, text)


def _write_voice_launcher() -> None:
    path = PROJECT_ROOT / "scripts/start_nexa_drive_voice_runtime.py"
    _write(path, '''#!/usr/bin/env python3
"""Start NeXa in real voice mode with mobile-base drive mode prepared."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A36029146-if00"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start NeXa with real wake-word listening and drive mode prepared."
    )
    parser.add_argument("--enable-movement", action="store_true")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-profile", default="wheel", choices=["ros", "wheel", "pwm"])
    parser.add_argument("--linear-speed-mps", type=float, default=0.18)
    parser.add_argument("--angular-speed-rad-s", type=float, default=0.65)
    parser.add_argument("--wheel-turn-speed-mps", type=float, default=0.26)
    parser.add_argument("--no-auto-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    main_py = project_root / "main.py"
    if not main_py.exists():
        raise SystemExit(f"main.py not found: {main_py}")

    env = os.environ.copy()
    env["NEXA_REQUIRE_REAL_VOICE_INPUT"] = "1"
    env["NEXA_REQUIRE_REAL_WAKE_GATE"] = "1"
    env["NEXA_RUNTIME_MODE"] = "voice_drive_runtime"
    env["NEXA_MOBILE_BASE_SERIAL_PORT"] = str(args.port)
    env["NEXA_DRIVE_MODE_HOST"] = str(args.host)
    env["NEXA_DRIVE_MODE_FORCE_RESTART"] = "1"
    env["NEXA_DRIVE_MODE_COMMAND_PROFILE"] = str(args.command_profile)
    env["NEXA_DRIVE_MODE_LINEAR_SPEED_MPS"] = f"{float(args.linear_speed_mps):.3f}"
    env["NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S"] = f"{float(args.angular_speed_rad_s):.3f}"
    env["NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS"] = f"{float(args.wheel_turn_speed_mps):.3f}"

    if args.no_auto_open:
        env.pop("NEXA_DRIVE_MODE_AUTO_OPEN", None)
    else:
        env["NEXA_DRIVE_MODE_AUTO_OPEN"] = "1"

    if args.enable_movement:
        env["CONFIRM_NEXA_MOBILE_BASE_TEST"] = "RUN"
        env["CONFIRM_NEXA_MOBILE_BASE_MOVE"] = "RUN"
        env["NEXA_DRIVE_MODE_ENABLE_MOVEMENT"] = "1"
        env.pop("NEXA_DRIVE_MODE_DRY_RUN", None)
        print("[START] Drive mode hardware movement gate: enabled")
    else:
        env.pop("CONFIRM_NEXA_MOBILE_BASE_MOVE", None)
        env.pop("NEXA_DRIVE_MODE_ENABLE_MOVEMENT", None)
        env["NEXA_DRIVE_MODE_DRY_RUN"] = "1"
        print("[START] Drive mode dry-run: enabled")

    print("[START] Real microphone/wake gate required: yes")
    print(f"[START] Project root: {project_root}")
    print(f"[START] Serial port: {env['NEXA_MOBILE_BASE_SERIAL_PORT']}")
    print(f"[START] Drive profile: {env['NEXA_DRIVE_MODE_COMMAND_PROFILE']}")
    print("[START] Launching main.py")
    return subprocess.call([sys.executable, str(main_py)], cwd=str(project_root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
''')
    path.chmod(0o755)


def _write_real_voice_check() -> None:
    path = PROJECT_ROOT / "scripts/check_nexa_real_voice_runtime.py"
    _write(path, '''#!/usr/bin/env python3
"""Check that NeXa can build real microphone + wake-word backends."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    os.environ["NEXA_REQUIRE_REAL_VOICE_INPUT"] = "1"
    os.environ["NEXA_REQUIRE_REAL_WAKE_GATE"] = "1"

    from modules.runtime.builder.core import RuntimeBuilder
    from modules.shared.config.settings import load_settings, reset_settings_cache

    reset_settings_cache()
    settings = load_settings()
    voice_input: dict[str, Any] = dict(settings.get("voice_input", {}) or {})
    print("[CHECK] Voice settings:")
    print(json.dumps({
        "enabled": voice_input.get("enabled"),
        "engine": voice_input.get("engine"),
        "wake_engine": voice_input.get("wake_engine"),
        "wake_model_path": voice_input.get("wake_model_path"),
        "wake_prefer_dedicated_gate": voice_input.get("wake_prefer_dedicated_gate"),
        "device_index": voice_input.get("device_index"),
        "device_name_contains": voice_input.get("device_name_contains"),
        "sample_rate": voice_input.get("sample_rate"),
    }, indent=2, sort_keys=True))

    try:
        runtime = RuntimeBuilder(settings=settings).build()
    except Exception as error:
        print(f"[CHECK FAIL] Real voice runtime could not be built: {type(error).__name__}: {error}")
        return 2

    statuses = {
        name: status.to_snapshot()
        for name, status in dict(runtime.backend_statuses).items()
        if name in {"voice_input", "wake_gate", "voice_output"}
    }
    print("[CHECK] Backend statuses:")
    print(json.dumps(statuses, indent=2, sort_keys=True))

    for obj in (getattr(runtime, "voice_input", None), getattr(runtime, "wake_gate", None), getattr(runtime, "voice_output", None)):
        close = getattr(obj, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    print("[CHECK OK] Real voice input and wake gate are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''')
    path.chmod(0o755)


def main() -> int:
    _patch_voice_input_mixin()
    _patch_wake_gate_mixin()
    _write_voice_launcher()
    _write_real_voice_check()
    print("[REPAIR OK] Real voice drive runtime launcher is installed and terminal fallback is blocked in strict mode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
