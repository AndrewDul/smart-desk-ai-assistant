"""Feedback lane — orchestrates the feedback dashboard lifecycle."""
from __future__ import annotations

import threading
import time
from typing import Any

from modules.shared.logging.logger import get_logger
from modules.runtime.turn_timeline import current_turn_id, log_turn_timeline

from .feedback_center_snapshot import build_feedback_center_snapshot
from .feedback_log_bridge import attach_feedback_log_handler, detach_feedback_log_handler, refresh_feedback_log_targets
from .feedback_vision_streamer import FeedbackVisionStreamer

LOGGER = get_logger(__name__)


class FeedbackLane:
    """Coordinator for feedback mode (dashboard + log bridge + vision stream)."""

    # Seconds to wait before starting camera — guarantees DIAGNOSTICS is rendered
    # in the Visual Shell before libcamera prints to stdout.
    _CAMERA_START_DELAY_S: float = 0.75
    # Give Godot at least one render opportunity before sending the first
    # structured status payload. Large RichTextLabel updates are intentionally
    # stage 2, after the lightweight diagnostics shell is visible.
    _FIRST_STATUS_SNAPSHOT_DELAY_S: float = 0.35

    def __init__(self, *, visual_shell_lane: Any, assistant: Any) -> None:
        self._visual_shell_lane = visual_shell_lane
        self._assistant = assistant
        self._lock = threading.Lock()
        self._streamer: FeedbackVisionStreamer | None = None
        self._status_thread: threading.Thread | None = None
        self._status_stop = threading.Event()
        self._cam_start_pending = threading.Event()
        self._active = False
        self._language = "en"

    @property
    def is_active(self) -> bool:
        return self._active

    def turn_on(self, *, language: str = "en") -> bool:
        with self._lock:
            self._language = str(language or "en")
            controller = self._controller()
            if controller is None:
                LOGGER.warning("Feedback lane: visual shell controller missing.")
                return False

            try:
                controller.show_feedback(
                    language=self._language,
                    source="nexa-feedback",
                    turn_id=current_turn_id(self._assistant),
                )
            except Exception as error:
                LOGGER.warning("Feedback lane: show_feedback failed safely: %s", error)
                return False

            attach_feedback_log_handler(controller)

            if self._active:
                LOGGER.info("Feedback mode: dashboard already active; refreshed shell only.")
                return True

            self._status_stop.clear()
            self._active = True

            cam = self._camera_service()
            if cam is not None:
                self._streamer = FeedbackVisionStreamer(controller, cam)
            else:
                LOGGER.warning("Feedback mode: no camera backend found, vision preview will stay empty.")

            self._status_thread = threading.Thread(
                target=self._status_loop,
                name="nexa-feedback-status",
                daemon=True,
            )
            self._status_thread.start()

        LOGGER.info("Feedback mode: dashboard started.")
        return True

    def turn_off(self) -> bool:
        controller = self._controller()

        # Hide immediately so the user never sees a frozen dashboard while
        # background workers are shutting down.
        if controller is not None:
            try:
                controller.hide_feedback(source="nexa-feedback")
            except Exception as error:
                LOGGER.warning("Feedback lane: immediate hide_feedback failed safely: %s", error)

        with self._lock:
            if not self._active:
                detach_feedback_log_handler()
                return False

            self._status_stop.set()
            status_thread = self._status_thread
            self._status_thread = None
            streamer = self._streamer
            self._streamer = None
            self._cam_start_pending.clear()
            self._active = False

        if streamer is not None:
            try:
                streamer.stop()
            except Exception:
                pass

        if status_thread is not None and status_thread.is_alive():
            status_thread.join(timeout=1.5)

        detach_feedback_log_handler()

        # Send hide again after worker shutdown. This is intentional and safe:
        # it makes the off command idempotent even if the first TCP message was
        # sent while the Visual Shell was busy.
        controller = self._controller()
        if controller is not None:
            try:
                controller.hide_feedback(source="nexa-feedback")
            except Exception as error:
                LOGGER.warning("Feedback lane: final hide_feedback failed safely: %s", error)

        LOGGER.info("Feedback mode: dashboard stopped.")
        return True

    def _controller(self) -> Any:
        lane = self._visual_shell_lane
        if lane is None:
            return None

        ctrl_factory = getattr(lane, "_controller", None)
        if callable(ctrl_factory):
            try:
                return ctrl_factory()
            except Exception:
                return None

        return getattr(lane, "controller", None)

    def _camera_service(self) -> Any:
        assistant = self._assistant
        if assistant is None:
            return None

        for attr in (
            "vision",
            "camera_service",
            "vision_service",
            "_camera_service",
        ):
            value = getattr(assistant, attr, None)
            if value is not None:
                return value

        runtime = getattr(assistant, "runtime", None)
        if runtime is not None:
            for attr in ("vision", "camera_service", "vision_service"):
                value = getattr(runtime, attr, None)
                if value is not None:
                    return value

            metadata = getattr(runtime, "metadata", None)
            if isinstance(metadata, dict):
                for key in ("vision_backend", "camera_service", "vision_service"):
                    value = metadata.get(key)
                    if value is not None:
                        return value

        return None

    def _status_loop(self) -> None:
        if self._status_stop.wait(timeout=self._FIRST_STATUS_SNAPSHOT_DELAY_S):
            return
        while not self._status_stop.is_set():
            try:
                self._publish_status_snapshot()
            except Exception as error:
                LOGGER.debug("Feedback status snapshot failed safely: %s", error)
            if self._status_stop.wait(timeout=2.5):
                break

    def _publish_status_snapshot(self) -> None:
        controller = self._controller()
        if controller is None:
            return

        refresh_feedback_log_targets()
        log_turn_timeline(self._assistant, event="status_snapshot_started")
        statuses = self._collect_statuses()
        center_snapshot = self._collect_feedback_center_snapshot(controller=controller)
        sections = center_snapshot.get("sections", [])
        send_started = time.monotonic()
        try:
            controller.feedback_status_update(
                statuses=statuses,
                sections=sections,
                source="nexa-feedback",
                turn_id=current_turn_id(self._assistant),
            )
            send_ms = (time.monotonic() - send_started) * 1000
            line = (
                "[visual-shell-latency] command=feedback_status_send "
                f"send_ms={send_ms:.1f} sections={len(sections)} statuses={len(statuses)}"
                + (
                    f" turn_id={current_turn_id(self._assistant)}"
                    if current_turn_id(self._assistant)
                    else ""
                )
            )
            print(line)
            LOGGER.info(line)
            log_turn_timeline(
                self._assistant,
                event="status_payload_sent",
                send_ms=send_ms,
                sections=len(sections),
                statuses=len(statuses),
            )
        except Exception as error:
            LOGGER.debug("Feedback status update failed safely: %s", error)

    def _collect_feedback_center_snapshot(self, *, controller: Any) -> dict[str, Any]:
        metrics_provider = getattr(controller, "metrics_provider", None)
        repo_root = "."
        assistant = self._assistant
        settings = getattr(assistant, "settings", {}) if assistant is not None else {}
        if isinstance(settings, dict):
            repo_root = str(settings.get("repo_root") or ".")
        started = time.monotonic()
        try:
            snapshot = build_feedback_center_snapshot(
                assistant=assistant,
                repo_root=repo_root,
                metrics_provider=metrics_provider,
            )
            elapsed_ms = (time.monotonic() - started) * 1000
            sections = snapshot.get("sections", [])
            item_count = 0
            for section in sections:
                if isinstance(section, dict):
                    items = section.get("items", [])
                    if isinstance(items, list):
                        item_count += len(items)
            line = (
                "[feedback-snapshot-latency] "
                f"build_ms={elapsed_ms:.1f} sections={len(sections)} items={item_count}"
                + (
                    f" turn_id={current_turn_id(assistant)}"
                    if current_turn_id(assistant)
                    else ""
                )
            )
            print(line)
            LOGGER.info(line)
            log_turn_timeline(
                assistant,
                event="status_snapshot_finished",
                build_ms=elapsed_ms,
                sections=len(sections),
                items=item_count,
            )
            return snapshot
        except Exception as error:
            elapsed_ms = (time.monotonic() - started) * 1000
            line = (
                "[feedback-snapshot-latency] "
                f"build_ms={elapsed_ms:.1f} sections=1 items=1 error=true"
            )
            print(line)
            LOGGER.info(line)
            log_turn_timeline(
                assistant,
                event="status_snapshot_finished",
                build_ms=elapsed_ms,
                sections=1,
                items=1,
                error=True,
            )
            LOGGER.debug("Feedback Center snapshot failed safely: %s", error)
            return {
                "sections": [
                    {
                        "id": "runtime",
                        "title": "Runtime Health",
                        "items": [
                            {
                                "label": "Feedback Center",
                                "value": "not available yet",
                                "hint": "Structured status collection failed safely.",
                                "severity": "warning",
                            }
                        ],
                    }
                ]
            }

    def _collect_statuses(self) -> dict:
        assistant = self._assistant
        statuses: dict[str, dict[str, str]] = {}

        def set_status(key: str, ok: bool, detail: str = "") -> None:
            statuses[key] = {
                "state": "ok" if ok else "not_ok",
                "detail": str(detail or "").strip(),
            }

        def backend_snapshot(component_name: str):
            backend_statuses = getattr(assistant, "backend_statuses", {}) if assistant is not None else {}
            status = backend_statuses.get(component_name)
            if status is None:
                return None

            detail = str(getattr(status, "detail", "") or "").strip()
            backend_label = str(getattr(status, "selected_backend", "") or "").strip()
            if backend_label and detail == "":
                detail = backend_label

            return {
                "ok": bool(getattr(status, "ok", False)),
                "detail": detail,
                "backend": backend_label,
            }

        # Core statuses
        core_map = {
            "llm": "llm",
            "camera": "vision",
            "lcd": "display",
            "microphone": "voice_input",
            "speaker": "voice_output",
            "stt": "voice_input",
            "tts": "voice_output",
            "wake": "wake",
        }

        for public_key, backend_key in core_map.items():
            snap = backend_snapshot(backend_key)
            if snap is not None:
                set_status(public_key, bool(snap["ok"]), snap["detail"])
            else:
                set_status(public_key, False, "status unavailable")

        # Refine STT / TTS from assistant surfaces when possible
        stt_service = getattr(assistant, "speech_recognition", None)
        if stt_service is not None:
            set_status("stt", True, "service ready")

        voice_out = getattr(assistant, "voice_out", None)
        if voice_out is not None:
            backend_name = getattr(voice_out, "backend_name", None) or getattr(voice_out, "engine", None)
            detail = str(backend_name or "output ready").strip()
            set_status("tts", True, detail if detail else "output ready")
            set_status("speaker", True, detail if detail else "output ready")

        wake_gate = getattr(assistant, "wake_gate", None)
        if wake_gate is not None:
            set_status("wake", True, "detector ready")

        # Vision-specific statuses
        cam = self._camera_service()
        if cam is None:
            set_status("vision_camera", False, "camera backend missing")
            set_status("vision_capture", False, "capture worker missing")
            set_status("vision_pipeline", False, "pipeline unavailable")
            set_status("vision_detection", False, "detector unavailable")
            return statuses

        cam_status_method = getattr(cam, "status", None)
        cam_status = {}
        if callable(cam_status_method):
            try:
                cam_status = cam_status_method() or {}
            except Exception as error:
                cam_status = {"ok": False, "last_error": str(error)}

        vision_ok = bool(cam_status.get("ok", True)) and not bool(cam_status.get("closed", False))
        if not bool(cam_status.get("enabled", True)):
            vision_ok = False

        camera_detail = str(cam_status.get("last_error") or cam_status.get("backend") or "").strip()
        if camera_detail == "" and bool(cam_status.get("enabled", True)):
            camera_detail = "camera backend ready"
        elif camera_detail == "":
            camera_detail = "disabled in config"

        set_status("vision_camera", vision_ok, camera_detail)

        worker = getattr(cam, "_worker", None)
        worker_running = False
        worker_detail = "capture worker missing"
        if worker is not None:
            worker_running = bool(getattr(worker, "is_running", False))
            worker_detail = "worker running" if worker_running else "worker stopped"

            stats_method = getattr(worker, "stats", None)
            if callable(stats_method):
                try:
                    worker_stats = stats_method() or {}
                    if not worker_running:
                        worker_running = bool(worker_stats.get("is_running", False))
                        worker_detail = "worker running" if worker_running else worker_detail
                except Exception:
                    pass

        set_status("vision_capture", worker_running, worker_detail)

        pipeline_ready = bool(cam_status.get("perception_pipeline_ready", False)) \
            and bool(cam_status.get("behavior_pipeline_ready", False)) \
            and bool(cam_status.get("stabilization_pipeline_ready", False)) \
            and bool(cam_status.get("session_tracker_ready", False))
        pipeline_detail = "pipelines ready" if pipeline_ready else "pipeline not ready"
        set_status("vision_pipeline", pipeline_ready, pipeline_detail)

        detector_ok = False
        detector_detail = "detector unavailable"
        detector_status_method = getattr(cam, "object_detector_status", None)
        if callable(detector_status_method):
            try:
                detector_status = detector_status_method()
            except Exception as error:
                detector_status = {"ok": False, "detail": str(error)}

            if isinstance(detector_status, dict):
                detector_ok = bool(
                    detector_status.get("ok", False)
                    or detector_status.get("ready", False)
                    or detector_status.get("enabled", False)
                )
                detector_detail = str(
                    detector_status.get("detail")
                    or detector_status.get("backend")
                    or detector_status.get("model_name")
                    or detector_status.get("name")
                    or ""
                ).strip()
                if detector_detail == "":
                    detector_detail = "detector ready" if detector_ok else "detector not ready"

        set_status("vision_detection", detector_ok, detector_detail)
        return statuses


    def schedule_post_response_camera_start(self, delay_seconds: float = 0.25) -> None:
        """Schedule camera.start() after the spoken/display response is delivered.

        Called from _handle_feedback_on() *after* _deliver_simple_action_response()
        returns, so DIAGNOSTICS is already on screen before libcamera prints to stdout.
        """
        cam = self._camera_service()
        if cam is None:
            return
        saved = self._CAMERA_START_DELAY_S
        self._CAMERA_START_DELAY_S = delay_seconds
        self._schedule_delayed_camera_start(cam)
        self._CAMERA_START_DELAY_S = saved

    def _schedule_delayed_camera_start(self, cam: Any) -> None:
        """Schedule camera.start() in a background thread after _CAMERA_START_DELAY_S.

        Idempotent: no-op if a start is already pending.  The delay guarantees
        the Visual Shell has received and rendered DIAGNOSTICS before libcamera
        prints its initialisation block to stdout.
        """
        if self._cam_start_pending.is_set():
            return
        if not callable(getattr(cam, "start", None)):
            return
        self._cam_start_pending.set()
        delay = self._CAMERA_START_DELAY_S
        print(f"[diagnostics-camera] scheduled delay_ms={delay * 1000:.0f}")
        LOGGER.info("[diagnostics-camera] scheduled delay_ms=%.0f", delay * 1000)
        threading.Thread(
            target=self._delayed_camera_worker,
            args=(cam, delay),
            name="nexa-feedback-cam-delayed-start",
            daemon=True,
        ).start()

    def _delayed_camera_worker(self, cam: Any, delay_seconds: float) -> None:
        try:
            time.sleep(delay_seconds)

            if not self._active:
                LOGGER.info("[diagnostics-camera] skipped (feedback inactive after delay)")
                return

            worker = getattr(cam, "_worker", None)
            if worker is not None and bool(getattr(worker, "is_running", False)):
                LOGGER.info("[diagnostics-camera] skipped (worker already running)")
                self._start_vision_streamer_if_needed()
                return

            print("[diagnostics-camera] starting delayed camera")
            LOGGER.info("[diagnostics-camera] starting delayed camera")
            _t0 = time.monotonic()
            try:
                cam.start()
                elapsed_ms = (time.monotonic() - _t0) * 1000
                print(f"[diagnostics-camera] started ok=true start_ms={elapsed_ms:.1f}")
                LOGGER.info("[diagnostics-camera] started ok=true start_ms=%.1f", elapsed_ms)
                self._start_vision_streamer_if_needed()
            except Exception as error:
                print(f"[diagnostics-camera] error={error}")
                LOGGER.warning("[diagnostics-camera] delayed camera start failed: %s", error)
        finally:
            self._cam_start_pending.clear()

    def _start_vision_streamer_if_needed(self) -> None:
        streamer = self._streamer
        if streamer is None:
            return
        try:
            streamer.start()
        except Exception as error:
            LOGGER.debug("Feedback vision streamer start failed safely: %s", error)


__all__ = ["FeedbackLane"]
