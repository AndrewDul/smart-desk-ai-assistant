from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import BoundingBox, FaceDetection
from modules.devices.vision.preprocessing import frame_to_bgr


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(slots=True)
class OpenCvHaarFaceDetector:
    backend_label: str = "opencv_haar"
    min_area_ratio: float = 0.002
    use_clahe: bool = True
    roi_enabled: bool = True
    roi_bounds: tuple[float, float, float, float] = (0.15, 0.05, 0.85, 0.78)
    scale_factor: float = 1.1
    min_neighbors: int = 5
    cascade: Any | None = field(default=None, repr=False)

    def detect_faces(self, packet: FramePacket) -> tuple[FaceDetection, ...]:
        gray, x_offset, y_offset = self._prepare_gray_frame(packet)
        cascade = self._get_cascade()

        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
        )

        frame_area = max(1, int(packet.width) * int(packet.height))
        results: list[FaceDetection] = []

        for x, y, width, height in faces:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)

            if width <= 0 or height <= 0:
                continue

            left = x_offset + x
            top = y_offset + y
            right = left + width
            bottom = top + height

            left = max(0, min(packet.width - 1, left))
            top = max(0, min(packet.height - 1, top))
            right = max(left + 1, min(packet.width, right))
            bottom = max(top + 1, min(packet.height, bottom))

            box = BoundingBox(left=left, top=top, right=right, bottom=bottom)
            area_ratio = (box.width * box.height) / frame_area
            if area_ratio < self.min_area_ratio:
                continue

            confidence = self._estimate_confidence(area_ratio, packet.height, box.height)

            results.append(
                FaceDetection(
                    bounding_box=box,
                    confidence=confidence,
                    label="face",
                    metadata={
                        "detector": self.backend_label,
                        "area_ratio": round(area_ratio, 5),
                    },
                )
            )

        return tuple(results)

    def _prepare_gray_frame(self, packet: FramePacket):
        import cv2

        bgr = frame_to_bgr(packet)

        if self.roi_enabled:
            x_min, y_min, x_max, y_max = self.roi_bounds
            x1 = max(0, min(packet.width - 1, int(round(packet.width * x_min))))
            y1 = max(0, min(packet.height - 1, int(round(packet.height * y_min))))
            x2 = max(x1 + 1, min(packet.width, int(round(packet.width * x_max))))
            y2 = max(y1 + 1, min(packet.height, int(round(packet.height * y_max))))
            bgr = bgr[y1:y2, x1:x2]
            x_offset = x1
            y_offset = y1
        else:
            x_offset = 0
            y_offset = 0

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        if self.use_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        return gray, x_offset, y_offset

    def _estimate_confidence(self, area_ratio: float, frame_height: int, face_height: int) -> float:
        height_ratio = face_height / max(1, frame_height)
        base = 0.55
        base += min(0.20, area_ratio * 20.0)
        base += min(0.15, height_ratio * 1.5)
        return _clamp(base, 0.0, 0.95)

    def _candidate_cascade_paths(self) -> tuple[Path, ...]:
        import cv2

        candidates: list[Path] = []
        filename = "haarcascade_frontalface_default.xml"

        cv2_data = getattr(cv2, "data", None)
        haar_dir = getattr(cv2_data, "haarcascades", None) if cv2_data is not None else None
        if haar_dir:
            candidates.append(Path(haar_dir) / filename)

        cv2_file = getattr(cv2, "__file__", None)
        if cv2_file:
            cv2_dir = Path(cv2_file).resolve().parent
            candidates.extend(
                [
                    cv2_dir / "data" / filename,
                    cv2_dir / "haarcascades" / filename,
                    cv2_dir.parent / "share" / "opencv4" / "haarcascades" / filename,
                    cv2_dir.parent / "share" / "opencv" / "haarcascades" / filename,
                ]
            )

        candidates.extend(
            [
                Path("/usr/share/opencv4/haarcascades") / filename,
                Path("/usr/share/opencv/haarcascades") / filename,
                Path("/usr/local/share/opencv4/haarcascades") / filename,
                Path("/usr/local/share/opencv/haarcascades") / filename,
            ]
        )

        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            resolved = str(candidate)
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_candidates.append(candidate)

        return tuple(unique_candidates)

    def _get_cascade(self):
        if self.cascade is None:
            import cv2

            cascade_path = None
            for candidate in self._candidate_cascade_paths():
                if candidate.is_file():
                    cascade_path = candidate
                    break

            if cascade_path is None:
                searched = "\n".join(str(path) for path in self._candidate_cascade_paths())
                raise RuntimeError(
                    "Failed to locate face cascade file 'haarcascade_frontalface_default.xml'. "
                    f"Searched paths:\n{searched}"
                )

            cascade = cv2.CascadeClassifier(str(cascade_path))
            if cascade.empty():
                raise RuntimeError(f"Failed to load face cascade: {cascade_path}")

            self.cascade = cascade

        return self.cascade