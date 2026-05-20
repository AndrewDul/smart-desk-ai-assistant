"""Non-streaming OAK-D Lite / DepthAI device status probe."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable


OAK_USB_MARKERS = ("luxonis", "movidius", "myriad", "03e7", "oak", "depthai")
OAK_MODEL_LABEL = "Luxonis OAK-D Lite Fixed Focus / DepthAI"
CAMERA_MODULE_LABEL = "Camera Module 3 Wide / picamera2"


def run_command(cmd: list[str], timeout: float = 4.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"command not found: {cmd[0]}", "returncode": 127}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"timeout after {timeout}s", "returncode": -1}
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": -2}


def matching_oak_usb_lines(text: str) -> list[str]:
    return [
        line
        for line in str(text or "").splitlines()
        if any(marker in line.lower() for marker in OAK_USB_MARKERS)
    ]


def load_vision_settings(settings_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    vision = payload.get("vision", {}) if isinstance(payload, dict) else {}
    if not isinstance(vision, dict):
        return {"error": "vision settings are not an object"}
    return {
        "enabled": vision.get("enabled"),
        "backend": vision.get("backend"),
        "fallback_backend": vision.get("fallback_backend"),
        "camera_index": vision.get("camera_index"),
        "object_detector_backend": vision.get("object_detector_backend"),
    }


def repo_has_oak_runtime_adapter(vision_root: Path) -> bool:
    """Return True only for a real runtime adapter, not this status probe."""

    search_roots = [
        vision_root / "capture",
        vision_root / "camera_service",
    ]
    marker_pattern = re.compile(r"\b(depthai|luxonis|oak)\b", flags=re.IGNORECASE)
    adapter_pattern = re.compile(
        r"(FrameSource|CameraService|DepthAI|DepthAi|Oak)",
        flags=re.IGNORECASE,
    )

    for root in search_roots:
        if not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                path = Path(dirpath) / filename
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if marker_pattern.search(text) and adapter_pattern.search(text):
                    return True
    return False


def enumerate_depthai_devices(
    *,
    module_available: Callable[[str], bool] | None = None,
    import_depthai: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    module_available = module_available or (
        lambda name: importlib.util.find_spec(name) is not None
    )
    if not module_available("depthai"):
        return {
            "depthai_available": False,
            "available_devices": [],
            "error": "depthai module not installed",
        }

    try:
        dai = import_depthai() if import_depthai is not None else __import__("depthai")
        devices = list(dai.Device.getAllAvailableDevices())
        return {
            "depthai_available": True,
            "available_devices": [_device_info_to_status(device) for device in devices],
            "error": "",
        }
    except Exception as exc:
        return {
            "depthai_available": True,
            "available_devices": [],
            "error": str(exc),
        }


def build_camera_module_status(vision_settings: dict[str, Any]) -> dict[str, Any]:
    backend = str(vision_settings.get("backend") or "").strip().lower()
    fallback = str(vision_settings.get("fallback_backend") or "").strip().lower()
    return {
        "id": "camera_module_3_wide",
        "label": CAMERA_MODULE_LABEL,
        "type": "runtime_camera",
        "backend": backend or "not configured",
        "fallback_backend": fallback or "not configured",
        "object_detector_backend": vision_settings.get("object_detector_backend"),
        "camera_index": vision_settings.get("camera_index"),
        "configured_enabled": bool(vision_settings.get("enabled", False)),
        "active_runtime_backend": backend == "picamera2",
        "active_streaming": bool(vision_settings.get("enabled", False)),
    }


def build_oak_depthai_status(
    *,
    lsusb_text: str,
    lsusb_returncode: int,
    lsusb_error: str,
    depthai_status: dict[str, Any],
    repo_has_adapter: bool,
) -> dict[str, Any]:
    matching_lines = matching_oak_usb_lines(lsusb_text)
    devices = list(depthai_status.get("available_devices") or [])
    device_count = len(devices)
    return {
        "id": "oak_d_lite_fixed_focus",
        "label": OAK_MODEL_LABEL,
        "type": "diagnostic_camera",
        "backend": "depthai",
        "usb_detected": bool(matching_lines),
        "usb_matches": matching_lines,
        "lsusb_returncode": int(lsusb_returncode),
        "lsusb_error": str(lsusb_error or "").strip(),
        "depthai_available": bool(depthai_status.get("depthai_available", False)),
        "depthai_device_count": device_count,
        "devices": devices,
        "device_info": devices[0] if devices else {},
        "mxid": _first_device_value(devices, "mxid"),
        "state": _first_device_value(devices, "state"),
        "repo_has_oak_adapter": bool(repo_has_adapter),
        "active_streaming": False,
        "recommended_next_step": _recommended_next_step(
            depthai_available=bool(depthai_status.get("depthai_available", False)),
            device_count=device_count,
            repo_has_adapter=bool(repo_has_adapter),
        ),
        "error": str(depthai_status.get("error") or ""),
    }


def build_vision_camera_status(
    *,
    settings_path: Path,
    vision_root: Path,
    run: Callable[[list[str]], dict[str, Any]] | None = None,
    module_available: Callable[[str], bool] | None = None,
    import_depthai: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    run = run or (lambda cmd: run_command(cmd))
    vision_settings = load_vision_settings(settings_path)
    lsusb = run(["lsusb"])
    lsusb_text = str(lsusb.get("stdout") or "") + str(lsusb.get("stderr") or "")
    depthai_status = enumerate_depthai_devices(
        module_available=module_available,
        import_depthai=import_depthai,
    )
    adapter_available = repo_has_oak_runtime_adapter(vision_root)

    camera_module = build_camera_module_status(vision_settings)
    oak = build_oak_depthai_status(
        lsusb_text=lsusb_text,
        lsusb_returncode=int(lsusb.get("returncode", -2)),
        lsusb_error=str(lsusb.get("stderr") or ""),
        depthai_status=depthai_status,
        repo_has_adapter=adapter_available,
    )

    return {
        "camera_sources": [camera_module, oak],
        "configured_vision_backend": vision_settings,
        "oak_d_lite": oak,
        "camera_module_3_wide": camera_module,
    }


def _device_info_to_status(device: Any) -> dict[str, Any]:
    text = str(device)
    return {
        "repr": text,
        "name": _read_device_attr(device, "name") or _parse_named_value(text, "name"),
        "mxid": (
            _read_device_attr(device, "mxid")
            or _read_device_attr(device, "deviceId")
            or _read_device_attr(device, "device_id")
            or _call_device_method(device, "getMxId")
            or _parse_named_value(text, "deviceId")
        ),
        "state": _clean_xlink_value(
            _read_device_attr(device, "state") or _parse_xlink_state(text)
        ),
        "protocol": _clean_xlink_value(
            _read_device_attr(device, "protocol") or _parse_xlink_protocol(text)
        ),
    }


def _read_device_attr(device: Any, name: str) -> str:
    try:
        value = getattr(device, name)
    except Exception:
        return ""
    if callable(value):
        return ""
    return str(value) if value not in (None, "") else ""


def _call_device_method(device: Any, name: str) -> str:
    method = getattr(device, name, None)
    if not callable(method):
        return ""
    try:
        value = method()
    except Exception:
        return ""
    return str(value) if value not in (None, "") else ""


def _parse_named_value(text: str, key: str) -> str:
    match = re.search(rf"{re.escape(key)}=([^,\)]+)", text)
    return match.group(1).strip() if match else ""


def _parse_xlink_state(text: str) -> str:
    for token in text.replace(")", "").split(","):
        value = token.strip()
        if value.startswith("X_LINK_") and value not in {
            "X_LINK_USB_VSC",
            "X_LINK_USB_CDC",
            "X_LINK_MYRIAD_X",
            "X_LINK_SUCCESS",
        }:
            return value
    return ""


def _parse_xlink_protocol(text: str) -> str:
    tokens = [token.strip().replace(")", "") for token in text.split(",")]
    protocols = [token for token in tokens if token in {"X_LINK_USB_VSC", "X_LINK_USB_CDC"}]
    return protocols[0] if protocols else ""


def _clean_xlink_value(value: str) -> str:
    text = str(value or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _first_device_value(devices: Iterable[dict[str, Any]], key: str) -> str:
    for device in devices:
        value = str(device.get(key) or "").strip()
        if value:
            return value
    return ""


def _recommended_next_step(
    *,
    depthai_available: bool,
    device_count: int,
    repo_has_adapter: bool,
) -> str:
    if not depthai_available:
        return "Install depthai in the runtime environment, then rerun the non-streaming probe."
    if device_count <= 0:
        return "Check USB cable, power, permissions, and udev rules, then rerun Device.getAllAvailableDevices()."
    if not repo_has_adapter:
        return "Add a non-default OAK runtime adapter after a separate RGB/depth smoke test."
    return "Adapter exists; keep OAK disabled by default until an explicit smoke test enables streaming."
