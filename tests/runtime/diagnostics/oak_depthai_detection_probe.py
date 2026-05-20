"""Safely enumerate Luxonis OAK/DepthAI availability without streaming frames."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[3]
SETTINGS_PATH = BASE_DIR / "config" / "settings.json"
VISION_DIR = BASE_DIR / "modules" / "devices" / "vision"

OAK_MARKERS = ("luxonis", "movidius", "myriad", "03e7", "oak", "depthai")


def _run(cmd: list[str], timeout: float = 4.0) -> dict[str, Any]:
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


def _matching_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if any(marker in line.lower() for marker in OAK_MARKERS)
    ]


def _depthai_devices() -> dict[str, Any]:
    if importlib.util.find_spec("depthai") is None:
        return {
            "depthai_available": False,
            "available_devices": [],
            "error": "depthai module not installed",
        }
    try:
        import depthai as dai

        devices = dai.Device.getAllAvailableDevices()
        return {
            "depthai_available": True,
            "available_devices": [str(device) for device in devices],
            "error": "",
        }
    except Exception as exc:
        return {
            "depthai_available": True,
            "available_devices": [],
            "error": str(exc),
        }


def _configured_vision_backend(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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


def _repo_has_oak_adapter(root: Path = VISION_DIR) -> bool:
    if not root.exists():
        return False
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                continue
            if "depthai" in text or "luxonis" in text or "oak" in text:
                return True
    return False


def build_report() -> dict[str, Any]:
    lsusb = _run(["lsusb"])
    depthai = _depthai_devices()
    return {
        "probe": "oak_depthai_detection_probe",
        "lsusb_returncode": lsusb["returncode"],
        "lsusb_matching_devices": _matching_lines(lsusb["stdout"] + lsusb["stderr"]),
        "lsusb_error": lsusb["stderr"].strip(),
        "depthai_available": depthai["depthai_available"],
        "depthai_available_devices": depthai["available_devices"],
        "depthai_error": depthai["error"],
        "configured_vision_backend": _configured_vision_backend(),
        "repo_has_oak_adapter": _repo_has_oak_adapter(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
