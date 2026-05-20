"""OAK-D Lite RGB/depth preview smoke probe.

Starts the OAK preview service, waits for a target number of RGB frames,
saves preview images to var/reports/, and prints a JSON report.

Usage:
    .venv/bin/python -m tests.runtime.diagnostics.oak_depthai_rgb_depth_smoke_probe
    .venv/bin/python -m tests.runtime.diagnostics.oak_depthai_rgb_depth_smoke_probe --frames 30
    .venv/bin/python -m tests.runtime.diagnostics.oak_depthai_rgb_depth_smoke_probe --timeout 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

REPORTS_DIR = BASE_DIR / "var" / "reports"

from modules.devices.vision.oak_depthai.preview_service import get_preview_service


def main() -> int:
    parser = argparse.ArgumentParser(description="OAK-D Lite RGB/depth smoke probe")
    parser.add_argument(
        "--frames", type=int, default=30,
        help="Number of RGB frames to wait for (default 30)",
    )
    parser.add_argument(
        "--timeout", type=float, default=20.0,
        help="Max seconds to wait for frames (default 20.0)",
    )
    args = parser.parse_args()
    target_frames = max(1, args.frames)
    timeout_s = max(5.0, args.timeout)

    svc = get_preview_service()

    report: dict = {
        "probe": "oak_depthai_rgb_depth_smoke_probe",
        "rgb_frames": 0,
        "depth_frames": 0,
        "first_rgb_frame_ms": None,
        "first_depth_frame_ms": None,
        "avg_fps": 0.0,
        "device_mxid": "",
        "usb_protocol": "",
        "errors": [],
        "saved_rgb_preview": None,
        "saved_depth_preview": None,
    }

    if not svc.start():
        err = svc.last_error or "start() returned False"
        report["errors"].append(f"OAK preview service failed to start: {err}")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    started_at = time.monotonic()
    first_rgb_ms: float | None = None
    first_depth_ms: float | None = None

    try:
        while True:
            elapsed = time.monotonic() - started_at
            rgb_count = svc.rgb_frame_count
            depth_count = svc.depth_frame_count

            if first_rgb_ms is None and rgb_count > 0:
                first_rgb_ms = elapsed * 1000.0
            if first_depth_ms is None and depth_count > 0:
                first_depth_ms = elapsed * 1000.0

            pipeline_err = svc.last_error
            if pipeline_err:
                report["errors"].append(f"Pipeline error: {pipeline_err}")
                break

            if rgb_count >= target_frames:
                break

            if elapsed >= timeout_s:
                if rgb_count == 0:
                    report["errors"].append(
                        f"Timeout after {timeout_s:.0f}s with no RGB frames. "
                        f"last_error={svc.last_error!r}"
                    )
                break

            time.sleep(0.1)

        report["rgb_frames"] = svc.rgb_frame_count
        report["depth_frames"] = svc.depth_frame_count
        report["first_rgb_frame_ms"] = (
            round(first_rgb_ms, 1) if first_rgb_ms is not None else None
        )
        report["first_depth_frame_ms"] = (
            round(first_depth_ms, 1) if first_depth_ms is not None else None
        )
        report["avg_fps"] = round(svc.fps, 1)
        report["device_mxid"] = svc.device_mxid

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")

        rgb_frame = svc.latest_rgb_frame()
        if rgb_frame is not None:
            saved = _save_jpeg(rgb_frame, REPORTS_DIR / f"oak_rgb_preview_{ts}.jpg")
            if saved:
                report["saved_rgb_preview"] = str(saved)

        depth_frame = svc.latest_depth_frame()
        if depth_frame is not None:
            saved = _save_png(depth_frame, REPORTS_DIR / f"oak_depth_preview_{ts}.png")
            if saved:
                report["saved_depth_preview"] = str(saved)

    finally:
        final_err = svc.last_error
        svc.stop()
        if final_err and final_err not in str(report["errors"]):
            report["errors"].append(f"last_error on stop: {final_err}")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["rgb_frames"] > 0 else 1


def _save_jpeg(frame, path: Path) -> Path | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        arr = np.asarray(frame.pixels)
        cv2.imwrite(str(path), arr)
        return path
    except Exception:
        pass
    try:
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
        arr = np.asarray(frame.pixels)
        img = Image.fromarray(arr.astype("uint8"))
        img.save(str(path), format="JPEG", quality=85)
        return path
    except Exception:
        return None


def _save_png(frame, path: Path) -> Path | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        arr = np.asarray(frame.pixels)
        cv2.imwrite(str(path), arr)
        return path
    except Exception:
        pass
    try:
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
        arr = np.asarray(frame.pixels)
        img = Image.fromarray(arr.astype("uint8"))
        img.save(str(path), format="PNG")
        return path
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
