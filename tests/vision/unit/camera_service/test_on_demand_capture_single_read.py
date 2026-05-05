from __future__ import annotations

from modules.devices.vision.camera_service.service import CameraService


class _FakeReader:
    def __init__(self) -> None:
        self.read_count = 0

    def read_frame(self) -> object:
        self.read_count += 1
        return {"frame": self.read_count}


def test_on_demand_capture_reads_exactly_one_frame_before_pipeline() -> None:
    service = object.__new__(CameraService)
    reader = _FakeReader()
    service._reader = reader

    captured_packets: list[object] = []

    def _run_pipeline(packet: object) -> object:
        captured_packets.append(packet)
        return {"observation": packet}

    service._run_pipeline = _run_pipeline

    result = CameraService._capture_once_locked(service)

    assert reader.read_count == 1
    assert captured_packets == [{"frame": 1}]
    assert result == {"observation": {"frame": 1}}
