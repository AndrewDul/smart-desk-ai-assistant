#!/usr/bin/env python3
"""
Focus Mode perception debug tool.

Captures one live frame from Picamera2 and runs every detector used by the
Focus Mode runtime:
  - OpenCV Haar face detection (current config + relaxed fallback)
  - OpenCV HOG person detection
  - Hailo YOLOv11 object detection (if Hailo is available)

Prints raw detection results with labels, confidence, and bounding boxes.
Saves an annotated debug JPEG to var/reports/focus_perception_debug_<ts>.jpg.

No pan-tilt movement. No config changes. Read-only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Repo root on path so module imports resolve.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_settings() -> dict:
    path = REPO_ROOT / "config" / "settings.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_frame(vision_cfg: dict):
    """Open Picamera2 briefly, capture one frame, close."""
    from modules.devices.vision.capture.picamera2_source import Picamera2FrameSource
    source = Picamera2FrameSource(
        frame_width=int(vision_cfg.get("frame_width", 640)),
        frame_height=int(vision_cfg.get("frame_height", 360)),
        warmup_seconds=1.5,
        hflip=bool(vision_cfg.get("hflip", False)),
        vflip=bool(vision_cfg.get("vflip", False)),
    )
    print("[capture] Opening Picamera2 …")
    source.open()
    print("[capture] Capturing frame …")
    packet = source.read_frame()
    # Close the camera immediately after capture.
    try:
        cam = getattr(source, "_camera", None)
        if cam is not None:
            cam.stop()
            cam.close()
    except Exception:
        pass
    print(f"[capture] Frame captured: {packet.width}x{packet.height} channels={packet.channels} backend={packet.backend_label}")
    return packet


def _run_haar_face_detection(packet, vision_cfg: dict, label: str, min_neighbors: int, profile_sweep: bool, equalized: bool, clahe: bool, scale_width: int):
    from modules.devices.vision.perception.face.opencv_haar_detector import OpenCvHaarFaceDetector
    detector = OpenCvHaarFaceDetector(
        min_area_ratio=float(vision_cfg.get("face_detector_min_area_ratio", 0.0015)),
        use_clahe=clahe,
        roi_enabled=bool(vision_cfg.get("face_detector_roi_enabled", False)),
        scale_width=scale_width,
        scale_factor=float(vision_cfg.get("face_detector_scale_factor", 1.1)),
        min_neighbors=min_neighbors,
        profile_sweep_enabled=profile_sweep,
        equalized_variant_enabled=equalized,
        min_size_px=int(vision_cfg.get("face_detector_min_size_px", 24)),
    )
    t0 = time.perf_counter()
    faces = detector.detect_faces(packet)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\n[face/{label}] min_neighbors={min_neighbors} profile_sweep={profile_sweep} equalized={equalized} clahe={clahe} scale_width={scale_width} → {len(faces)} face(s) in {elapsed_ms:.1f} ms")
    for i, face in enumerate(faces):
        box = face.bounding_box
        print(f"  [{i}] conf={face.confidence:.3f} box=[{box.left},{box.top},{box.right},{box.bottom}] area_ratio={face.metadata.get('area_ratio')} profile={face.metadata.get('cascade_profile')}")
    return faces


def _run_hog_people_detection(packet, vision_cfg: dict):
    from modules.devices.vision.perception.people.opencv_hog_detector import OpenCvHogPeopleDetector
    detector = OpenCvHogPeopleDetector(
        min_confidence=float(vision_cfg.get("people_detector_min_confidence", 0.45)),
        min_area_ratio=float(vision_cfg.get("people_detector_min_area_ratio", 0.025)),
        min_height_ratio=float(vision_cfg.get("people_detector_min_height_ratio", 0.18)),
        max_width_ratio=float(vision_cfg.get("people_detector_max_width_ratio", 0.85)),
        use_clahe=bool(vision_cfg.get("people_detector_use_clahe", True)),
        upscale_factor=float(vision_cfg.get("people_detector_upscale_factor", 1.35)),
        desk_roi_enabled=bool(vision_cfg.get("people_detector_desk_roi_enabled", True)),
        desk_roi_bounds=(
            float(vision_cfg.get("people_detector_roi_x_min", 0.1)),
            float(vision_cfg.get("people_detector_roi_y_min", 0.08)),
            float(vision_cfg.get("people_detector_roi_x_max", 0.9)),
            float(vision_cfg.get("people_detector_roi_y_max", 0.98)),
        ),
    )
    t0 = time.perf_counter()
    people = detector.detect_people(packet)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\n[hog_people] → {len(people)} person(s) in {elapsed_ms:.1f} ms")
    for i, person in enumerate(people):
        box = person.bounding_box
        print(f"  [{i}] conf={person.confidence:.3f} box=[{box.left},{box.top},{box.right},{box.bottom}] source={person.metadata.get('source','hog')}")
    return people


def _run_hailo_yolo(packet, vision_cfg: dict):
    hef_path = vision_cfg.get("object_detector_hailo_hef_path", "/usr/share/hailo-models/yolov11m_h10.hef")
    if not Path(hef_path).exists():
        print(f"\n[hailo_yolo] HEF not found at {hef_path} — skipping.")
        return ()
    try:
        from modules.devices.vision.perception.objects.hailo_yolo_detector import HailoYoloObjectDetector
        detector = HailoYoloObjectDetector(
            hef_path=hef_path,
            score_threshold=float(vision_cfg.get("object_detector_hailo_score_threshold", 0.35)),
            max_detections=int(vision_cfg.get("object_detector_hailo_max_detections", 30)),
            desk_relevant_only=False,
            initial_cadence_hz=10.0,
        )
        t0 = time.perf_counter()
        objects = detector.detect_objects(packet)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if detector._unavailable_reason:
            print(f"\n[hailo_yolo] Hailo unavailable: {detector._unavailable_reason}")
            return ()
        print(f"\n[hailo_yolo] → {len(objects)} object(s) in {elapsed_ms:.1f} ms (threshold={detector.score_threshold})")
        for i, obj in enumerate(objects):
            box = obj.bounding_box
            print(f"  [{i}] label={obj.label!r:20s} conf={obj.confidence:.3f} box=[{box.left},{box.top},{box.right},{box.bottom}] class_idx={obj.metadata.get('class_index')}")
        detector.close()
        return objects
    except Exception as error:
        print(f"\n[hailo_yolo] Error: {error}")
        return ()


def _save_debug_image(packet, faces_current, faces_relaxed, hog_people, hailo_objects, out_path: Path) -> None:
    try:
        import cv2
        import numpy as np
        from modules.devices.vision.preprocessing import frame_to_bgr
        bgr = frame_to_bgr(packet).copy()

        # Hailo objects — gray
        for obj in hailo_objects:
            b = obj.bounding_box
            color = (180, 180, 180)
            if obj.label == "person":
                color = (255, 128, 0)  # orange for YOLO person
            elif obj.label == "cell phone":
                color = (0, 255, 255)  # cyan for phone
            cv2.rectangle(bgr, (b.left, b.top), (b.right, b.bottom), color, 1)
            cv2.putText(bgr, f"{obj.label} {obj.confidence:.2f}", (b.left, max(10, b.top - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

        # HOG people — blue
        for person in hog_people:
            b = person.bounding_box
            cv2.rectangle(bgr, (b.left, b.top), (b.right, b.bottom), (255, 50, 50), 2)
            cv2.putText(bgr, f"hog {person.confidence:.2f}", (b.left, max(10, b.top - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 50, 50), 1, cv2.LINE_AA)

        # Haar faces (current config) — red
        for face in faces_current:
            b = face.bounding_box
            cv2.rectangle(bgr, (b.left, b.top), (b.right, b.bottom), (0, 0, 255), 2)
            cv2.putText(bgr, f"haar_strict {face.confidence:.2f}", (b.left, min(packet.height - 4, b.bottom + 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)

        # Haar faces (relaxed) — green
        for face in faces_relaxed:
            b = face.bounding_box
            cv2.rectangle(bgr, (b.left, b.top), (b.right, b.bottom), (50, 200, 50), 2)
            cv2.putText(bgr, f"haar_relaxed {face.confidence:.2f}", (b.left, min(packet.height - 4, b.bottom + 26)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 200, 50), 1, cv2.LINE_AA)

        legend = [
            "orange=YOLO person  cyan=YOLO phone  gray=YOLO other",
            "blue=HOG person  red=Haar(strict mn=6)  green=Haar(relaxed mn=3)",
        ]
        for j, line in enumerate(legend):
            cv2.putText(bgr, line, (6, 14 + j * 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1, cv2.LINE_AA)

        cv2.imwrite(str(out_path), bgr)
        print(f"\n[debug_image] Saved: {out_path}")
    except Exception as error:
        print(f"\n[debug_image] Could not save debug image: {error}")


def main() -> None:
    settings = _load_settings()
    vision_cfg = settings.get("vision", {})

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = REPO_ROOT / "var" / "reports" / f"focus_perception_debug_{ts}.jpg"

    print("=" * 60)
    print("Focus Mode Perception Debug")
    print(f"  Frame size : {vision_cfg.get('frame_width')}x{vision_cfg.get('frame_height')}")
    print(f"  hflip={vision_cfg.get('hflip')}  vflip={vision_cfg.get('vflip')}")
    print(f"  face backend : {vision_cfg.get('face_detector_backend')}")
    print(f"  face min_neighbors (current) : {vision_cfg.get('face_detector_min_neighbors')}")
    print(f"  face scale_width (current) : {vision_cfg.get('face_detector_scale_width')}")
    print(f"  people backend : {vision_cfg.get('people_detector_backend')}")
    print(f"  hog_secondary_enabled : {vision_cfg.get('people_detector_hybrid_use_hog_secondary')}")
    print(f"  hailo hef : {vision_cfg.get('object_detector_hailo_hef_path')}")
    print("=" * 60)

    packet = _capture_frame(vision_cfg)

    # A: Haar — current config (strict)
    faces_current = _run_haar_face_detection(
        packet, vision_cfg,
        label="CURRENT (strict)",
        min_neighbors=int(vision_cfg.get("face_detector_min_neighbors", 6)),
        profile_sweep=bool(vision_cfg.get("face_detector_profile_sweep_enabled", False)),
        equalized=bool(vision_cfg.get("face_detector_equalized_variant_enabled", False)),
        clahe=bool(vision_cfg.get("face_detector_use_clahe", False)),
        scale_width=int(vision_cfg.get("face_detector_scale_width", 360)),
    )

    # B: Haar — relaxed (min_neighbors=3, profile sweep, equalized, clahe, full width)
    faces_relaxed = _run_haar_face_detection(
        packet, vision_cfg,
        label="RELAXED (mn=3, sweep, eq, clahe, full-width)",
        min_neighbors=3,
        profile_sweep=True,
        equalized=True,
        clahe=True,
        scale_width=0,  # no downscale
    )

    # C: HOG people (direct, no face projection)
    hog_people = _run_hog_people_detection(packet, vision_cfg)

    # D: Hailo YOLO
    hailo_objects = _run_hailo_yolo(packet, vision_cfg)

    # E: Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  A. Haar faces (current config, strict) : {len(faces_current)}")
    print(f"  B. Haar faces (relaxed config)         : {len(faces_relaxed)}")
    print(f"  C. HOG people (direct)                 : {len(hog_people)}")
    yolo_person = [o for o in hailo_objects if o.label == "person"]
    yolo_phone  = [o for o in hailo_objects if o.label == "cell phone"]
    print(f"  D. YOLO objects total                  : {len(hailo_objects)}")
    print(f"     ↳ person (class 0)                  : {len(yolo_person)}")
    print(f"     ↳ cell phone (class 67)             : {len(yolo_phone)}")
    print()
    if len(faces_current) == 0 and len(faces_relaxed) > 0:
        print("  DIAGNOSIS: Haar FAILS with current params but SUCCEEDS when relaxed.")
        print("  Root cause: face_detector_min_neighbors=6 too strict (or scale/clahe combination).")
        print("  Fix: reduce min_neighbors to 3-4, enable profile_sweep + equalized_variant.")
    elif len(faces_current) == 0 and len(faces_relaxed) == 0 and len(yolo_person) > 0:
        print("  DIAGNOSIS: Haar FAILS (even relaxed). YOLO detects person.")
        print("  YOLO person detection is present but NOT fed into people_count.")
        print("  Fix: bridge YOLO 'person' label into FocusVisionObservationReader people_count.")
    elif len(faces_current) > 0:
        print("  Haar detects face(s) with current config — face detection is working.")
        print("  If people_count=0, check hybrid detector wiring or presence behavior logic.")
    else:
        print("  DIAGNOSIS: Haar FAILS (even relaxed), YOLO detects NO person either.")
        print("  Camera may not be seeing the user — check orientation, zoom, position.")
    print("=" * 60)

    _save_debug_image(packet, faces_current, faces_relaxed, hog_people, hailo_objects, out_path)
    print(f"\nDebug image: {out_path}")


if __name__ == "__main__":
    main()
