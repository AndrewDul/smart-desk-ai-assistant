from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.runtime.builder.core import RuntimeBuilder
from modules.runtime.builder.look_at_me_mixin import LookAtMeSession
from modules.shared.config.settings import load_settings


LOOK_AT_ME_STATUS_PATH = PROJECT_ROOT / "var/data/look_at_me_tracking_status.json"
VISION_TRACKING_STATUS_PATH = PROJECT_ROOT / "var/data/vision_tracking_status.json"


class _DiagnosticVisionBackend:
    def start(self) -> None:
        return None

    def latest_observation(self, *, force_refresh: bool = False) -> None:
        del force_refresh
        return None


class _DiagnosticPanTiltBackend:
    def status(self) -> dict[str, Any]:
        return {
            "pan_angle": 0.0,
            "tilt_angle": 0.0,
            "safe_limits": {
                "pan_min_degrees": -89.67,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 89.67,
                "tilt_min_degrees": -12.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 80.0,
            },
        }


class _DiagnosticTrackingService:
    def status(self) -> dict[str, Any]:
        return {"ok": True, "diagnostic_stub": True}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"_missing": True, "_path": str(path)}
    except Exception as error:
        return {"_error": f"{type(error).__name__}: {error}", "_path": str(path)}


def _class_evidence(obj_or_class: Any) -> dict[str, Any]:
    cls = obj_or_class if inspect.isclass(obj_or_class) else obj_or_class.__class__
    return {
        "class": cls.__name__,
        "module": cls.__module__,
        "source_file": inspect.getsourcefile(cls),
        "has_send_velocity": callable(getattr(obj_or_class, "send_velocity", None)),
        "has_open": callable(getattr(obj_or_class, "open", None)),
        "has_close": callable(getattr(obj_or_class, "close", None)),
        "has_read_available_lines": callable(getattr(obj_or_class, "read_available_lines", None)),
        "has_stop": callable(getattr(obj_or_class, "stop", None)),
        "public_methods": sorted(
            name
            for name in dir(obj_or_class)
            if not name.startswith("_") and callable(getattr(obj_or_class, name, None))
        ),
    }


def _find_look_at_me_session_classes() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted((PROJECT_ROOT / "modules").rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "class LookAtMeSession" not in text:
            continue
        results.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "contains_class_look_at_me_session": True,
            }
        )
    return results


def _extract_live_tilt_evidence(
    *,
    look_status: dict[str, Any],
    tracking_status: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    last_iteration = look_status.get("last_iteration")
    if not isinstance(last_iteration, dict):
        last_iteration = {}
    plan = last_iteration.get("plan")
    if not isinstance(plan, dict):
        plan = tracking_status.get("last_plan") if isinstance(tracking_status.get("last_plan"), dict) else {}
    diagnostics = plan.get("diagnostics") if isinstance(plan.get("diagnostics"), dict) else {}

    pan_tilt = settings.get("pan_tilt") if isinstance(settings.get("pan_tilt"), dict) else {}
    limits = pan_tilt.get("safe_limits") if isinstance(pan_tilt.get("safe_limits"), dict) else {}

    tilt_command = last_iteration.get("tilt_command_degrees", look_status.get("tilt_command_degrees"))
    no_tilt_below_center = bool(settings.get("look_at_me", {}).get("no_tilt_below_center", False))
    failure = bool(
        no_tilt_below_center
        and isinstance(tilt_command, (int, float))
        and float(tilt_command) < 0.0
    )
    return {
        "safe_limits": {
            "tilt_min_degrees": limits.get("tilt_min_degrees"),
            "tilt_center_degrees": limits.get("tilt_center_degrees"),
            "tilt_max_degrees": limits.get("tilt_max_degrees"),
        },
        "current_tilt_angle": look_status.get("tilt_angle"),
        "requested_tilt_delta_before_clamp": diagnostics.get("raw_tilt_delta_degrees"),
        "final_tilt_delta_after_clamp": plan.get("tilt_delta_degrees", tilt_command),
        "look_at_me_status_tilt_command_degrees": tilt_command,
        "look_at_me_status_tilt_clamped_to_center": last_iteration.get(
            "tilt_clamped_to_center",
            look_status.get("tilt_clamped_to_center"),
        ),
        "config_no_tilt_below_center": no_tilt_below_center,
        "policy_no_tilt_below_center_from_plan": diagnostics.get("no_tilt_below_center"),
        "policy_tilt_clamped_to_center_from_plan": diagnostics.get("tilt_clamped_to_center"),
        "failure_negative_tilt_while_no_tilt_below_center": failure,
    }


def _extract_yaw_evidence(
    *,
    look_status: dict[str, Any],
    tracking_status: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    last_iteration = look_status.get("last_iteration")
    if not isinstance(last_iteration, dict):
        last_iteration = {}
    plan = tracking_status.get("last_plan")
    if not isinstance(plan, dict):
        plan = last_iteration.get("plan") if isinstance(last_iteration.get("plan"), dict) else {}
    execution = tracking_status.get("last_execution_result")
    if not isinstance(execution, dict):
        execution = last_iteration.get("execution_result") if isinstance(last_iteration.get("execution_result"), dict) else {}

    yaw_assist = last_iteration.get("yaw_assist") if isinstance(last_iteration.get("yaw_assist"), dict) else {}
    look_config = settings.get("look_at_me") if isinstance(settings.get("look_at_me"), dict) else {}
    return {
        "mobile_base_yaw_assist_enabled": look_status.get(
            "mobile_base_yaw_assist_enabled",
            look_config.get("mobile_base_yaw_assist_enabled"),
        ),
        "mobile_base_contact_required_for_yaw": look_config.get(
            "mobile_base_contact_required_for_yaw"
        ),
        "mobile_base_yaw_assist_active": look_status.get("mobile_base_yaw_assist_active"),
        "mobile_base_contact_ok": look_status.get("mobile_base_contact_ok"),
        "mobile_base_yaw_assist_available": look_status.get("mobile_base_yaw_assist_available"),
        "last_mobile_base_command": look_status.get("last_mobile_base_command"),
        "last_mobile_base_error": look_status.get("last_mobile_base_error"),
        "last_yaw_assist_error": look_status.get("last_yaw_assist_error"),
        "plan": {
            "base_yaw_assist_required": plan.get("base_yaw_assist_required"),
            "base_yaw_direction": plan.get("base_yaw_direction"),
            "pan_at_limit": plan.get("pan_at_limit"),
            "reason": plan.get("reason"),
        },
        "execution_block_reason": execution.get("execution_block_reason"),
        "execution_status": execution.get("status"),
        "yaw_assist_result_from_look_iteration": yaw_assist,
        "send_yaw_assist_called_in_last_iteration": bool(
            yaw_assist and yaw_assist.get("requested") is not False
        ),
        "send_yaw_assist_not_called_reason": (
            yaw_assist.get("reason")
            if yaw_assist and yaw_assist.get("requested") is False
            else None
        ),
        "linear_x_mps_would_be_zero": True,
    }


def _command_stream_evidence(look_status: dict[str, Any]) -> dict[str, Any]:
    last_iteration = look_status.get("last_iteration")
    if not isinstance(last_iteration, dict):
        last_iteration = {}
    command = {
        "pan_command_degrees": last_iteration.get(
            "pan_command_degrees",
            look_status.get("pan_command_degrees"),
        ),
        "tilt_command_degrees": last_iteration.get(
            "tilt_command_degrees",
            look_status.get("tilt_command_degrees"),
        ),
        "has_target": last_iteration.get("has_target"),
        "reason": last_iteration.get("reason"),
    }
    return {
        "tracking_state": look_status.get("tracking_state"),
        "has_target": last_iteration.get("has_target"),
        "last_face_seen_age_ms": None,
        "scan_called_while_tracking_face": bool(
            look_status.get("tracking_state") == "tracking_face"
            and last_iteration.get("search_active")
        ),
        "scan_command_count_while_has_target_true": None,
        "zero_between_nonzero_count": None,
        "command_stream_sample": [command],
    }


def _builder_probe(settings: dict[str, Any]) -> dict[str, Any]:
    builder = RuntimeBuilder(settings=settings)
    mobility_config = dict(settings.get("mobility", {}) or {})
    mobility_backend, mobility_status = builder._build_mobility(mobility_config)
    session, look_status = builder._build_look_at_me_session(
        vision_backend=_DiagnosticVisionBackend(),
        pan_tilt_backend=_DiagnosticPanTiltBackend(),
        vision_tracking_service=_DiagnosticTrackingService(),
        mobility_backend=mobility_backend,
    )
    session_backend = getattr(session, "_mobility_backend", None) if session is not None else None
    return {
        "runtime_builder": _class_evidence(builder),
        "runtime_builder_mro": [
            f"{cls.__module__}.{cls.__name__}" for cls in RuntimeBuilder.__mro__
        ],
        "mobility_config_loaded_by_runtime": {
            key: mobility_config.get(key)
            for key in (
                "enabled",
                "dry_run",
                "port",
                "movement_enabled",
                "require_movement_confirm_env",
                "command_profile",
            )
        },
        "mobility_backend_status": mobility_status.to_snapshot(),
        "mobility_backend_object": _class_evidence(mobility_backend),
        "look_at_me_builder_status": look_status.to_snapshot(),
        "look_at_me_session_object": None if session is None else _class_evidence(session),
        "look_at_me_session_mobility_backend_object": (
            None if session_backend is None else _class_evidence(session_backend)
        ),
        "look_at_me_session_status": None if session is None else session.status(),
    }


def build_report(*, output: Path | None = None) -> dict[str, Any]:
    settings = load_settings()
    look_status = _read_json(LOOK_AT_ME_STATUS_PATH)
    tracking_status = _read_json(VISION_TRACKING_STATUS_PATH)
    builder_probe = _builder_probe(settings)

    report = {
        "generated_at_unix": time.time(),
        "project_root": str(PROJECT_ROOT),
        "status_files": {
            "look_at_me_tracking_status_path": str(LOOK_AT_ME_STATUS_PATH),
            "vision_tracking_status_path": str(VISION_TRACKING_STATUS_PATH),
            "look_at_me_tracking_status": look_status,
            "vision_tracking_status": tracking_status,
        },
        "live_runtime_builder_wiring": {
            "builder_probe_note": (
                "This probe uses the current repository RuntimeBuilder methods with diagnostic "
                "vision/pan-tilt/tracking stubs, and reads live status JSON for the active process."
            ),
            **builder_probe,
            "look_at_me_session_implementations": _find_look_at_me_session_classes(),
            "runtime_look_at_me_session_class": _class_evidence(LookAtMeSession),
            "look_at_me_constructor_signature": str(inspect.signature(LookAtMeSession)),
        },
        "mobility_backend_evidence": {
            "env": {
                "CONFIRM_NEXA_MOBILE_BASE_MOVE": os.environ.get("CONFIRM_NEXA_MOBILE_BASE_MOVE"),
                "NEXA_DRIVE_MODE_ENABLE_MOVEMENT": os.environ.get("NEXA_DRIVE_MODE_ENABLE_MOVEMENT"),
                "NEXA_MOBILE_BASE_SERIAL_PORT": os.environ.get("NEXA_MOBILE_BASE_SERIAL_PORT"),
            },
            **{
                key: builder_probe[key]
                for key in (
                    "mobility_config_loaded_by_runtime",
                    "mobility_backend_status",
                    "mobility_backend_object",
                    "look_at_me_session_mobility_backend_object",
                )
            },
        },
        "yaw_assist_evidence": _extract_yaw_evidence(
            look_status=look_status,
            tracking_status=tracking_status,
            settings=settings,
        ),
        "tilt_clamp_evidence": _extract_live_tilt_evidence(
            look_status=look_status,
            tracking_status=tracking_status,
            settings=settings,
        ),
        "tracking_search_evidence": _command_stream_evidence(look_status),
        "test_gap_evidence": {
            "tests/runtime/builder/test_look_at_me_yaw_assist.py": [
                "Uses a fake mobility backend unless compared with builder_probe.",
                "Does not read live var/data/look_at_me_tracking_status.json.",
                "Does not prove the active process is using the same class object.",
            ],
            "tests/runtime/builder/test_look_at_me_smooth_tracking.py": [
                "Uses a fake pan-tilt backend.",
                "Measures adapter command generation, not physical servo motion.",
                "Does not assert against live status JSON.",
            ],
            "tests/runtime/validation/test_mobile_base_yaw_assist_validation.py": [
                "Validates builder and command shape in-process.",
                "Does not prove the live process loaded mobility.enabled=true.",
                "Does not open real hardware unless config/env allow it.",
            ],
            "tests/benchmarks/vision/test_look_at_me_smoothness_benchmark.py": [
                "Benchmarks command generation only.",
                "Does not validate camera detections, serial latency, or live status files.",
            ],
        },
    }

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def _default_output_path() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "var/reports" / f"look_at_me_runtime_evidence_{stamp}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect look-at-me runtime wiring evidence.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--print", action="store_true", dest="print_report")
    args = parser.parse_args(argv)

    output = args.output or _default_output_path()
    report = build_report(output=output)
    print(f"[diagnostic] wrote {output}")
    if args.print_report:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
