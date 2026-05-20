"""Safely enumerate Luxonis OAK/DepthAI availability without streaming frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.devices.vision.oak_depthai.device_probe import build_vision_camera_status


BASE_DIR = Path(__file__).resolve().parents[3]
SETTINGS_PATH = BASE_DIR / "config" / "settings.json"
VISION_DIR = BASE_DIR / "modules" / "devices" / "vision"

def build_report() -> dict[str, Any]:
    status = build_vision_camera_status(
        settings_path=SETTINGS_PATH,
        vision_root=VISION_DIR,
    )
    oak = status["oak_d_lite"]
    return {
        "probe": "oak_depthai_detection_probe",
        **status,
        "lsusb_returncode": oak["lsusb_returncode"],
        "lsusb_matching_devices": oak["usb_matches"],
        "lsusb_error": oak["lsusb_error"],
        "depthai_available": oak["depthai_available"],
        "depthai_available_devices": oak["devices"],
        "depthai_error": oak["error"],
        "repo_has_oak_adapter": oak["repo_has_oak_adapter"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
