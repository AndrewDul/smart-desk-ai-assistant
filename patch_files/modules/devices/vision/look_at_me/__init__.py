"""
NEXA Look-At-Me — in-process face tracking session.

This package provides a single-process, single-camera-owner implementation of
the "look at me" / "popatrz na mnie" voice command. It deliberately replaces
the previous subprocess-based architecture, which fought with the main
CameraService over Picamera2 ownership ("Device or resource busy" errors).

Public surface:
    - LookAtMeSession: start()/stop() lifecycle, runs a worker thread that
      reads VisionObservation from the existing CameraService and drives the
      pan/tilt backend directly.
"""
from .session import LookAtMeSession, LookAtMeStatus
from .scan_planner import ScanPlanner, ScanCommand
from .tracking_planner import TrackingPlanner, TrackingCommand

__all__ = [
    "LookAtMeSession",
    "LookAtMeStatus",
    "ScanPlanner",
    "ScanCommand",
    "TrackingPlanner",
    "TrackingCommand",
]
