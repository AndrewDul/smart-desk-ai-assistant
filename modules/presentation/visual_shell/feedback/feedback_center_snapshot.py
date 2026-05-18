"""Structured Feedback Center snapshot builder."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.presentation.visual_shell.service import VisualShellSystemMetricsProvider


Severity = str


@dataclass(slots=True)
class FeedbackCenterSnapshotBuilder:
    assistant: Any
    repo_root: Path = Path(".")
    metrics_provider: VisualShellSystemMetricsProvider | None = None

    def build(self) -> dict[str, Any]:
        current_activity = self._current_activity_payload()
        recent_activity_events = self._diagnostics_events()
        sections = [
            self._overview_section(activity_payload=current_activity),
            self._activity_section(events=recent_activity_events),
            self._performance_section(),
            self._runtime_section(),
            self._llm_section(),
            self._audio_section(),
            self._tests_section(),
            self._logs_section(),
            self._memory_section(),
            self._vision_section(),
            self._power_section(),
        ]
        return {
            "schema_version": 1,
            "generated_at_ms": int(time.time() * 1000),
            "current_activity": current_activity,
            "recent_activity_events": recent_activity_events,
            "sections": sections,
        }

    def _current_activity_payload(self) -> dict[str, Any]:
        runtime_snapshot = self._runtime_product_snapshot()
        command_policy = dict(getattr(self.assistant, "_last_command_window_policy_snapshot", {}) or {})
        route_snapshot = self._last_route_snapshot()
        response_snapshot = dict(getattr(self.assistant, "_last_response_delivery_snapshot", {}) or {})
        capture = dict(getattr(self.assistant, "_last_input_capture", {}) or {})
        activity = self._current_activity(
            runtime_snapshot=runtime_snapshot,
            command_policy=command_policy,
            route_snapshot=route_snapshot,
            response_snapshot=response_snapshot,
        )
        warning = self._latest_warning(runtime_snapshot=runtime_snapshot, response_snapshot=response_snapshot)
        backend = self._last_backend_used(
            capture=capture,
            route_snapshot=route_snapshot,
            response_snapshot=response_snapshot,
        )
        route = route_snapshot.get("route_kind") or response_snapshot.get("route_kind") or ""
        return {
            "activity_state": activity,
            "last_transcript": str(capture.get("text") or ""),
            "last_language": str(capture.get("language") or getattr(self.assistant, "last_language", "") or ""),
            "last_route": str(route or ""),
            "last_backend_used": backend,
            "last_response_status": str(response_snapshot.get("source") or ""),
            "latest_warning_or_error": warning,
            "active_capture_mode": str(capture.get("mode") or command_policy.get("action") or ""),
            "is_listening": activity == "Listening",
            "is_speaking": activity == "Speaking",
            "is_thinking": activity == "Thinking",
            "used_llm": backend == "LLM",
            "used_fast_line": backend == "fast-line",
            "used_vosk": backend == "Vosk",
            "used_faster_whisper": backend == "FasterWhisper",
            "first_token_latency_ms": response_snapshot.get("first_token_latency_ms"),
            "first_speakable_chunk_latency_ms": response_snapshot.get("first_speakable_chunk_latency_ms"),
            "first_audio_ms": response_snapshot.get("first_audio_ms"),
            "route_to_first_audio_ms": response_snapshot.get("route_to_first_audio_ms"),
        }

    def _overview_section(self, *, activity_payload: dict[str, Any]) -> dict[str, Any]:
        warning = str(activity_payload.get("latest_warning_or_error") or "")
        return _section(
            "overview",
            "Overview",
            [
                _item("Activity state", activity_payload.get("activity_state"), "What NeXa appears to be doing right now.", _severity_from_activity(activity_payload.get("activity_state"))),
                _item("Last transcript", activity_payload.get("last_transcript") or "not available yet", "Latest accepted speech transcript."),
                _item("Last language", activity_payload.get("last_language") or "not available yet", "Language for the latest turn."),
                _item("Last route", activity_payload.get("last_route") or "not available yet", "Latest routing path."),
                _item("Last backend used", activity_payload.get("last_backend_used") or "unknown", "Backend or lane used by the latest turn."),
                _item("Last response status", activity_payload.get("last_response_status") or "not available yet", "Latest response delivery status/source."),
                _item("Latest warning/error", warning or "none", "Most recent warning or error surfaced to the product layer.", "warning" if warning else "ok"),
            ],
        )

    def _activity_section(self, *, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return _section(
                "activity",
                "Recent Activity",
                [
                    _item(
                        "Event timeline",
                        "not available yet",
                        "Recent runtime state changes appear here when the runtime exposes them.",
                        "unknown",
                    )
                ],
            )

        items: list[dict[str, Any]] = []
        for event in events[-12:]:
            message = str(event.get("message") or "not available yet")
            event_type = str(event.get("type") or "event")
            severity = str(event.get("severity") or "info")
            items.append(
                _item(
                    event_type.replace("_", " ").title(),
                    message,
                    "Recent runtime event.",
                    severity,
                )
            )
        return _section("activity", "Recent Activity", items)

    def _performance_section(self) -> dict[str, Any]:
        capture = dict(getattr(self.assistant, "_last_input_capture", {}) or {})
        route_snapshot = self._last_route_snapshot()
        response_snapshot = dict(getattr(self.assistant, "_last_response_delivery_snapshot", {}) or {})
        benchmark_snapshot = self._benchmark_snapshot()
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})
        summary = dict(benchmark_snapshot.get("summary", {}) or {})

        items: list[dict[str, Any]] = [
            _item(
                "Last command",
                _first_present(latest_sample.get("user_text_preview"), capture.get("text"), "unavailable"),
                "Heard text from the latest completed or captured command.",
            ),
            _item(
                "Language",
                _first_present(latest_sample.get("language"), capture.get("language"), getattr(self.assistant, "last_language", ""), "unavailable"),
                "Language attached to the latest turn.",
            ),
            _item(
                "STT backend",
                _first_present(latest_sample.get("stt_backend_label"), capture.get("backend"), capture.get("engine"), "unavailable"),
                "Speech-to-text backend from cached runtime state.",
            ),
            _item(
                "Route / source",
                _first_present(latest_sample.get("route_kind"), route_snapshot.get("route_kind"), response_snapshot.get("route_kind"), response_snapshot.get("source"), "unavailable"),
                "Latest command route or response source.",
            ),
            _item(
                "Canonical intent",
                _first_present(latest_sample.get("canonical_intent"), latest_sample.get("primary_intent"), route_snapshot.get("canonical_intent"), route_snapshot.get("primary_intent"), "not measured yet"),
                "Canonical intent when the router or benchmark exposes it.",
            ),
            _item(
                "LLM prevented",
                _bool_or_unavailable(latest_sample.get("llm_prevented")),
                "Whether the latest command explicitly avoided LLM routing.",
            ),
            _item(
                "Result / status",
                _first_present(latest_sample.get("result"), response_snapshot.get("status"), response_snapshot.get("source"), "unavailable"),
                "Latest completed result or response status.",
            ),
        ]

        timing_pairs = [
            ("action_ms", latest_sample.get("skill_latency_ms")),
            ("turn_on_ms", latest_sample.get("wake_to_listen_ms")),
            ("turn_off_ms", latest_sample.get("response_total_ms")),
            ("total_action_ms", _first_present(latest_sample.get("total_action_ms"), latest_sample.get("total_turn_ms"), summary.get("last_total_turn_ms"))),
            ("TTS first audio", _first_present(response_snapshot.get("first_audio_ms"), latest_sample.get("response_first_audio_ms"))),
            ("route_to_first_audio", _first_present(latest_sample.get("route_to_first_audio_ms"), response_snapshot.get("route_to_first_audio_ms"))),
            ("skill_to_first_audio", latest_sample.get("skill_to_first_audio_ms")),
            ("total response time", latest_sample.get("response_total_ms")),
        ]
        has_timing = False
        for label, value in timing_pairs:
            rendered = _metric(value)
            if rendered != "not available yet":
                has_timing = True
            items.append(_item(label, rendered if rendered != "not available yet" else "not measured yet", "Latest cached turn timing."))

        event_items = self._performance_event_items(latest_sample)
        if event_items:
            items.extend(event_items)
        else:
            items.append(
                _item(
                    "Recent timing events",
                    "No timing data yet" if not has_timing else "not measured yet",
                    "Recent timing event rows appear here after a measured turn.",
                    "unknown",
                )
            )

        slowest_items = self._slowest_operation_items(latest_sample)
        if slowest_items:
            items.extend(slowest_items)
        else:
            items.append(
                _item(
                    "Slowest recent operations",
                    "No timing data yet" if not has_timing else "not measured yet",
                    "Slow operation ranking is derived only from cached benchmark metrics.",
                    "unknown",
                )
            )

        items.extend(self._subsystem_performance_items(latest_sample=latest_sample, response_snapshot=response_snapshot))

        if not latest_sample and not has_timing:
            items.insert(
                0,
                _item(
                    "Timing data",
                    "No timing data yet",
                    "Diagnostics did not find a completed in-memory turn benchmark.",
                    "unknown",
                ),
            )

        return _section("performance", "Performance / Timings", items)

    def _performance_event_items(self, latest_sample: dict[str, Any]) -> list[dict[str, Any]]:
        event_specs = [
            ("Voice", "wake", "Wake to listen", latest_sample.get("wake_to_listen_ms"), latest_sample.get("wake_source")),
            ("STT", "speech", "Listen to speech", latest_sample.get("listen_to_speech_ms"), latest_sample.get("stt_backend_label")),
            ("Routing", "route", "Speech to route", latest_sample.get("speech_to_route_ms"), latest_sample.get("route_kind")),
            ("Actions", "skill", "Skill execution", latest_sample.get("skill_execution_window_ms"), latest_sample.get("skill_status")),
            ("TTS", "response", "Response first audio", latest_sample.get("response_first_audio_ms"), latest_sample.get("response_source")),
            ("LLM", "llm", "LLM first chunk", latest_sample.get("llm_first_chunk_ms"), latest_sample.get("llm_source")),
        ]
        items: list[dict[str, Any]] = []
        for category, event, label, duration, metadata in event_specs:
            rendered = _metric(duration)
            if rendered == "not available yet":
                continue
            status = _first_present(latest_sample.get("result"), latest_sample.get("skill_status"), "measured")
            summary = _short_summary(
                {
                    "category": category,
                    "event": event,
                    "operation": label,
                    "duration_ms": duration,
                    "status": status,
                    "metadata": metadata,
                }
            )
            items.append(_item(f"Event: {category} / {label}", summary, "Cached timing event from the latest completed turn."))
        return items[:8]

    def _slowest_operation_items(self, latest_sample: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            ("Wake to listen", latest_sample.get("wake_to_listen_ms")),
            ("Listen to speech", latest_sample.get("listen_to_speech_ms")),
            ("Speech to route", latest_sample.get("speech_to_route_ms")),
            ("Route to first audio", latest_sample.get("route_to_first_audio_ms")),
            ("Skill execution", latest_sample.get("skill_execution_window_ms")),
            ("Skill to first audio", latest_sample.get("skill_to_first_audio_ms")),
            ("Response first audio", latest_sample.get("response_first_audio_ms")),
            ("Response total", latest_sample.get("response_total_ms")),
            ("LLM first chunk", latest_sample.get("llm_first_chunk_ms")),
            ("LLM total", latest_sample.get("llm_total_ms")),
            ("Total turn", latest_sample.get("total_turn_ms")),
        ]
        ranked: list[tuple[float, str]] = []
        for label, value in candidates:
            parsed = _safe_positive_float(value)
            if parsed is not None:
                ranked.append((parsed, label))
        ranked.sort(reverse=True)

        route = _first_present(latest_sample.get("route_kind"), latest_sample.get("primary_intent"), "")
        created = str(latest_sample.get("created_at_iso") or "").strip()
        suffix = ", ".join(str(part) for part in (f"when={created}" if created else "", f"route={route}" if route else "") if part)
        return [
            _item(
                f"Slow op: {label}",
                f"{duration:.1f} ms" + (f" ({suffix})" if suffix else ""),
                "Slowest cached operation from the latest benchmark sample.",
                "warning" if duration >= 1000.0 else "info",
            )
            for duration, label in ranked[:5]
        ]

    def _subsystem_performance_items(
        self,
        *,
        latest_sample: dict[str, Any],
        response_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        subsystem_specs = [
            ("Voice", _first_present(latest_sample.get("wake_latency_ms"), latest_sample.get("wake_to_listen_ms"))),
            ("STT", latest_sample.get("stt_latency_ms")),
            ("Command routing", latest_sample.get("speech_to_route_ms")),
            ("Actions", _first_present(latest_sample.get("skill_latency_ms"), latest_sample.get("skill_execution_window_ms"))),
            ("TTS", _first_present(response_snapshot.get("first_audio_ms"), latest_sample.get("response_first_audio_ms"))),
            ("Visual Shell", response_snapshot.get("visual_shell_ms")),
            ("Camera", latest_sample.get("camera_ms")),
            ("Vision", latest_sample.get("vision_ms")),
            ("Memory", latest_sample.get("memory_ms")),
            ("LLM", _first_present(latest_sample.get("llm_first_chunk_ms"), latest_sample.get("llm_total_ms"))),
        ]
        return [
            _item(
                f"Subsystem: {name}",
                _metric(value) if _metric(value) != "not available yet" else "not measured yet",
                "Subsystem timing is shown only when already measured by runtime telemetry.",
            )
            for name, value in subsystem_specs
        ]

    def _runtime_section(self) -> dict[str, Any]:
        runtime_snapshot = self._runtime_product_snapshot()
        command_policy = dict(getattr(self.assistant, "_last_command_window_policy_snapshot", {}) or {})
        route_snapshot = self._last_route_snapshot()
        response_snapshot = dict(getattr(self.assistant, "_last_response_delivery_snapshot", {}) or {})
        capture = dict(getattr(self.assistant, "_last_input_capture", {}) or {})

        warnings = runtime_snapshot.get("warnings") or runtime_snapshot.get("blockers") or []
        warning_text = ", ".join(str(item) for item in warnings[:3]) if isinstance(warnings, list) else ""
        voice_session = getattr(self.assistant, "voice_session", None)
        voice_state = _read_attr(voice_session, "state", "not available yet")

        return _section(
            "runtime",
            "Runtime Health",
            [
                _item("NeXa runtime status", _upper(runtime_snapshot.get("lifecycle_state")), "Current product runtime state.", _severity_from_runtime(runtime_snapshot)),
                _item("Voice mode", voice_state, "Current voice session mode or state."),
                _item("Wake / capture status", command_policy.get("action") or capture.get("mode") or "not available yet", "Latest wake or capture policy action."),
                _item("Last command", capture.get("text") or command_policy.get("text") or "not available yet", "Most recent captured command text."),
                _item("Last route", route_snapshot.get("route_kind") or route_snapshot.get("primary_intent") or response_snapshot.get("route_kind") or "not available yet", "Most recent route selected by NeXa."),
                _item("Last language", capture.get("language") or getattr(self.assistant, "last_language", "") or "not available yet", "Language used for the current or latest turn."),
                _item("Last response status", response_snapshot.get("source") or "not available yet", "Latest response delivery source."),
                _item("Warnings / errors", warning_text or "none", "Current startup/runtime warnings.", "warning" if warning_text else "ok"),
            ],
        )

    def _llm_section(self) -> dict[str, Any]:
        runtime_snapshot = self._runtime_product_snapshot()
        local_llm = self._local_llm()
        backend_info: dict[str, Any] = {}
        if local_llm is not None:
            describe_backend = getattr(local_llm, "describe_backend", None)
            if callable(describe_backend):
                backend_info = _safe_dict_call(describe_backend)
        response_snapshot = dict(getattr(self.assistant, "_last_response_delivery_snapshot", {}) or {})

        health = dict(backend_info.get("health", {}) or {})
        enabled = backend_info.get("enabled", runtime_snapshot.get("llm_enabled", False))
        state = health.get("state") or runtime_snapshot.get("llm_state") or "not available yet"
        last_error = (
            health.get("last_error")
            or backend_info.get("last_generation_error")
            or backend_info.get("server_availability_error")
            or runtime_snapshot.get("llm_health_reason")
            or ""
        )

        return _section(
            "llm",
            "LLM Backend",
            [
                _item("Enabled", _yes_no(enabled), "Whether local LLM dialogue is enabled."),
                _item("Backend type", backend_info.get("runner") or runtime_snapshot.get("llm_runner") or "not available yet", "Configured local LLM provider."),
                _item("Server URL", backend_info.get("server_url") or "not available yet", "Local HTTP endpoint used by NeXa."),
                _item("Readiness state", state, "Cached local LLM readiness state.", _severity_from_llm_state(state)),
                _item("Available / healthy", _yes_no(health.get("available", runtime_snapshot.get("llm_available", False))), "Whether the backend can answer now."),
                _item("Model name", backend_info.get("server_model_name") or "not available yet", "Configured model identifier."),
                _item("Last error", last_error or "none", "Most recent LLM backend error.", "warning" if last_error else "ok"),
                _item("first_token_latency_ms", _metric(response_snapshot.get("first_token_latency_ms") or backend_info.get("first_token_latency_ms")), "Time to first model token."),
                _item("first_speakable_chunk_latency_ms", _metric(response_snapshot.get("first_speakable_chunk_latency_ms") or backend_info.get("first_speakable_chunk_latency_ms")), "Time to first speakable streamed chunk."),
                _item("first_audio_ms", _metric(response_snapshot.get("first_audio_ms")), "Time until first spoken audio."),
                _item("route_to_first_audio_ms", _metric(response_snapshot.get("route_to_first_audio_ms")), "Route-to-audio latency for the latest response."),
                _item("Generation source", backend_info.get("last_generation_source") or response_snapshot.get("source") or "not available yet", "Latest LLM or response source."),
            ],
        )

    def _audio_section(self) -> dict[str, Any]:
        settings = getattr(self.assistant, "settings", {}) if self.assistant is not None else {}
        voice_input = settings.get("voice_input", {}) if isinstance(settings, dict) else {}
        capture = dict(getattr(self.assistant, "_last_input_capture", {}) or {})
        command_policy = dict(getattr(self.assistant, "_last_command_window_policy_snapshot", {}) or {})
        backend_statuses = getattr(self.assistant, "backend_statuses", {}) or {}
        voice_status = backend_statuses.get("voice_input")
        detail = _read_attr(voice_status, "detail", "")
        overflow = _first_present(
            capture.get("overflow_delta"),
            capture.get("overflow_count"),
            capture.get("input_overflow_count"),
            _nested(capture, "metadata", "overflow_delta"),
            "not available yet",
        )

        return _section(
            "audio",
            "Audio / ASR",
            [
                _item("Selected input device", voice_input.get("device_name_contains") or voice_input.get("device_index") or "not available yet", "Configured microphone selector."),
                _item("device_name_contains", voice_input.get("device_name_contains") or "not available yet", "Preferred input device name fragment."),
                _item("Backend", voice_input.get("engine") or detail or "not available yet", "Speech recognition backend."),
                _item("Capture profile", capture.get("capture_profile") or command_policy.get("capture_mode") or "not available yet", "Latest capture profile used."),
                _item("Active capture mode", capture.get("mode") or command_policy.get("action") or "not available yet", "Latest capture mode or policy action."),
                _item("Overflow counter", overflow, "FasterWhisper callback overflow count or delta.", "warning" if _is_positive_number(overflow) else "unknown" if overflow == "not available yet" else "ok"),
                _item("Last transcript", capture.get("text") or "not available yet", "Latest transcript accepted by the runtime."),
                _item("Detected language", capture.get("language") or "not available yet", "Language detected or selected for the latest capture."),
                _item("Conversation repair used", _yes_no(capture.get("mode") == "conversation_repair" or command_policy.get("action") == "conversation_repair"), "Whether the last turn used dialogue repair."),
                _item("Microphone status", detail or "not available yet", "Configured input backend status.", "warning" if voice_status is None else "ok"),
            ],
        )

    def _tests_section(self) -> dict[str, Any]:
        benchmark = self.repo_root / "var" / "data" / "turn_benchmarks.json"
        reports_dir = self.repo_root / "var" / "reports"
        latest_report = _latest_file(reports_dir)
        return _section(
            "tests",
            "Tests / Validations / Benchmarks",
            [
                _item("Turn benchmark file", _file_status(benchmark), "Latest persisted turn benchmark data."),
                _item("Latest report", str(latest_report.relative_to(self.repo_root)) if latest_report else "not available yet", "Newest validation/report artifact under var/reports."),
                _item("Validation status", "not available yet" if latest_report is None else "available", "Existing reports only; this UI does not run tests."),
            ],
        )

    def _logs_section(self) -> dict[str, Any]:
        log_candidates = [
            self.repo_root / "var" / "logs" / "system.log",
            self.repo_root / "var" / "logs" / "nexa.log",
        ]
        existing = next((path for path in log_candidates if path.exists()), None)
        return _section(
            "logs",
            "Logs",
            [
                _item("Live log bridge", "active when Feedback Center is open", "Runtime log lines are streamed into the Logs tab."),
                _item("Runtime log file", _file_status(existing) if existing else "not available yet", "Recent persistent runtime log if configured."),
            ],
        )

    def _memory_section(self) -> dict[str, Any]:
        memory = self._memory_service()
        if memory is None:
            return _section(
                "memory",
                "Memory",
                [
                    _item("Known people count", "not available yet", "Memory service is not exposed.", "unknown"),
                    _item("Known objects count", "not available yet", "Memory service is not exposed.", "unknown"),
                ],
            )
        people = _safe_list_call(getattr(memory, "list_people", None))
        objects = _safe_list_call(getattr(memory, "list_objects", None))
        top_people = ", ".join(_display_name(item) for item in people[:5]) or "not available yet"
        store_path = _read_attr(memory, "path", "") or _read_attr(memory, "memory_path", "") or "not available yet"
        return _section(
            "memory",
            "Memory",
            [
                _item("Known people count", len(people), "People currently available for recall and gallery."),
                _item("Known objects count", len(objects), "Objects currently available for recall and gallery."),
                _item("Top people", top_people, "First known people from memory index."),
                _item("Memory store path", store_path, "Memory storage path when exposed."),
            ],
        )

    def _vision_section(self) -> dict[str, Any]:
        camera = self._camera_service()
        cam_status = _safe_dict_call(getattr(camera, "status", None)) if camera is not None else {}
        worker = getattr(camera, "_worker", None) if camera is not None else None
        worker_stats = _safe_dict_call(getattr(worker, "stats", None)) if worker is not None else {}
        detector = _safe_dict_call(getattr(camera, "object_detector_status", None)) if camera is not None else {}
        runtime = getattr(self.assistant, "runtime", None)
        metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
        if not isinstance(metadata, dict):
            metadata = {}
        pan_tilt = metadata.get("pan_tilt_backend") or "not available yet"
        tracking = metadata.get("vision_tracking_status") or "not available yet"

        return _section(
            "vision",
            "Camera / Vision / Pan-Tilt",
            [
                _item("Camera status", cam_status.get("last_error") or ("ready" if cam_status else "not available yet"), "Camera backend status.", "warning" if cam_status.get("last_error") else "ok" if cam_status else "unknown"),
                _item("Camera backend", cam_status.get("backend") or "not available yet", "Configured camera backend."),
                _item("Capture worker", "running" if worker_stats.get("is_running") else "not available yet", "Live camera worker status."),
                _item("Detector status", detector.get("detail") or detector.get("backend") or "not available yet", "Object detector status."),
                _item("Latest observation age", _metric(cam_status.get("latest_observation_age_seconds"), suffix="s"), "Age of latest observation when available."),
                _item("Pan-tilt status", pan_tilt, "Pan-tilt backend or status metadata."),
                _item("Tracking status", tracking, "Vision tracking readiness/status metadata."),
            ],
        )

    def _power_section(self) -> dict[str, Any]:
        provider = self.metrics_provider or VisualShellSystemMetricsProvider()
        battery = provider.read_battery()
        temperature = provider.read_temperature()
        return _section(
            "power",
            "Power / Battery",
            [
                _item("Battery level", f"{battery.percent}%" if battery is not None else "not available", "Battery percentage if the hardware exposes it.", "ok" if battery is not None else "unknown"),
                _item("Battery source", battery.source if battery is not None else "not available", "Battery data source."),
                _item("Temperature", f"{temperature.value_c} C" if temperature is not None else "not available", "CPU/system temperature if available.", "ok" if temperature is not None else "unknown"),
                _item("Temperature source", temperature.source if temperature is not None else "not available", "Temperature data source."),
            ],
        )

    def _runtime_product_snapshot(self) -> dict[str, Any]:
        runtime_product = getattr(self.assistant, "runtime_product", None)
        snapshot_method = getattr(runtime_product, "snapshot", None)
        if callable(snapshot_method):
            return _safe_dict_call(snapshot_method)
        return {}

    def _benchmark_snapshot(self) -> dict[str, Any]:
        service = getattr(self.assistant, "turn_benchmark_service", None)

        latest_snapshot = getattr(service, "latest_snapshot", None)
        if callable(latest_snapshot):
            return _safe_dict_call(latest_snapshot)

        latest_summary = getattr(service, "latest_summary", None)
        if callable(latest_summary):
            summary = _safe_dict_call(latest_summary)
            return {"latest_sample": {}, "summary": summary, "overlay_lines": []}

        return {}

    def _last_route_snapshot(self) -> dict[str, Any]:
        for attr in ("_last_fast_lane_route_snapshot", "_last_route_snapshot"):
            value = getattr(self.assistant, attr, None)
            if isinstance(value, dict) and value:
                return dict(value)
        return {}

    def _local_llm(self) -> Any:
        dialogue = getattr(self.assistant, "dialogue", None)
        return getattr(dialogue, "local_llm", None) if dialogue is not None else None

    def _memory_service(self) -> Any:
        for attr in ("memory", "memory_service"):
            value = getattr(self.assistant, attr, None)
            if value is not None:
                return value
        runtime = getattr(self.assistant, "runtime", None)
        return getattr(runtime, "memory", None) if runtime is not None else None

    def _camera_service(self) -> Any:
        for attr in ("vision", "camera_service", "vision_service", "_camera_service"):
            value = getattr(self.assistant, attr, None)
            if value is not None:
                return value
        runtime = getattr(self.assistant, "runtime", None)
        if runtime is not None:
            metadata = getattr(runtime, "metadata", None)
            if isinstance(metadata, dict):
                return metadata.get("vision_backend") or metadata.get("camera_service")
        return None

    @staticmethod
    def _current_activity(
        *,
        runtime_snapshot: dict[str, Any],
        command_policy: dict[str, Any],
        route_snapshot: dict[str, Any],
        response_snapshot: dict[str, Any],
    ) -> str:
        state = str(runtime_snapshot.get("lifecycle_state") or "").strip().lower()
        if state in {"failed", "degraded"}:
            return "Error / degraded"
        route_kind = str(route_snapshot.get("route_kind") or response_snapshot.get("route_kind") or "").lower()
        source = str(response_snapshot.get("source") or "").lower()
        action = str(command_policy.get("action") or "").lower()
        if "llm" in source or route_kind == "conversation":
            return "Running LLM dialogue"
        if route_kind == "action":
            return "Running fast-line command"
        if "listen" in action or "capture" in action:
            return "Listening"
        if state == "ready":
            return "Waiting for wake word"
        if state == "booting":
            return "Thinking"
        return "Unknown"

    @staticmethod
    def _last_backend_used(
        *,
        capture: dict[str, Any],
        route_snapshot: dict[str, Any],
        response_snapshot: dict[str, Any],
    ) -> str:
        source = str(response_snapshot.get("source") or route_snapshot.get("source") or "").lower()
        route_kind = str(route_snapshot.get("route_kind") or response_snapshot.get("route_kind") or "").lower()
        capture_backend = str(capture.get("backend") or capture.get("engine") or "").strip()
        if route_kind == "conversation" or "llm" in source:
            return "LLM"
        if route_kind == "action":
            return "fast-line"
        if "memory" in source or route_kind == "memory":
            return "memory"
        if "vision" in source or route_kind == "vision":
            return "vision"
        if capture_backend:
            return capture_backend
        if capture.get("capture_profile") or capture.get("mode"):
            return "FasterWhisper"
        return "unknown"

    @staticmethod
    def _latest_warning(*, runtime_snapshot: dict[str, Any], response_snapshot: dict[str, Any]) -> str:
        for key in ("warnings", "blockers", "premium_blockers"):
            values = runtime_snapshot.get(key)
            if isinstance(values, list) and values:
                return str(values[0])
        error = response_snapshot.get("error")
        return str(error or "").strip()

    def _diagnostics_events(self) -> list[dict[str, Any]]:
        raw_events = getattr(self.assistant, "_diagnostics_events", None)
        if not isinstance(raw_events, list):
            return []
        events: list[dict[str, Any]] = []
        for event in raw_events[-30:]:
            if not isinstance(event, dict):
                continue
            events.append(
                {
                    "ts_ms": event.get("ts_ms"),
                    "type": str(event.get("type") or "event"),
                    "message": str(event.get("message") or "not available yet"),
                    "severity": str(event.get("severity") or "info"),
                    "metadata": dict(event.get("metadata", {}) or {})
                    if isinstance(event.get("metadata"), dict)
                    else {},
                }
            )
        return events


def build_feedback_center_snapshot(
    *,
    assistant: Any,
    repo_root: Path | str = ".",
    metrics_provider: VisualShellSystemMetricsProvider | None = None,
) -> dict[str, Any]:
    return FeedbackCenterSnapshotBuilder(
        assistant=assistant,
        repo_root=Path(repo_root),
        metrics_provider=metrics_provider,
    ).build()


def _section(section_id: str, title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": section_id, "title": title, "items": items}


def _item(label: str, value: object, hint: str, severity: Severity = "info") -> dict[str, Any]:
    return {
        "label": label,
        "value": _stringify(value),
        "hint": hint,
        "severity": severity if severity in {"ok", "info", "warning", "error", "unknown"} else "info",
    }


def _safe_dict_call(method: Any) -> dict[str, Any]:
    if not callable(method):
        return {}
    try:
        value = method()
    except Exception:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _safe_list_call(method: Any) -> list[dict[str, Any]]:
    if not callable(method):
        return []
    try:
        value = method(language=None)
    except TypeError:
        try:
            value = method()
        except Exception:
            return []
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _latest_file(path: Path) -> Path | None:
    if not path.exists() or not path.is_dir():
        return None
    candidates = [item for item in path.rglob("*") if item.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _file_status(path: Path | None) -> str:
    if path is None:
        return "not available yet"
    return str(path) if path.exists() else "not available yet"


def _display_name(item: dict[str, Any]) -> str:
    return str(item.get("display_name") or item.get("name") or item.get("id") or "").strip()


def _read_attr(obj: Any, attr: str, default: object = "") -> object:
    return getattr(obj, attr, default) if obj is not None else default


def _nested(payload: dict[str, Any], key: str, nested_key: str) -> object:
    value = payload.get(key)
    return value.get(nested_key) if isinstance(value, dict) else None


def _first_present(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _upper(value: object) -> str:
    text = str(value or "not available yet").strip()
    return text.upper() if text and text != "not available yet" else "not available yet"


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def _metric(value: object, *, suffix: str = "ms") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not available yet"
    if number <= 0.0:
        return "not available yet"
    return f"{number:.1f} {suffix}"


def _safe_positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0.0 else None


def _bool_or_unavailable(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "unavailable"


def _short_summary(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    category = str(payload.get("category") or "").strip()
    operation = str(payload.get("operation") or "").strip()
    duration = _metric(payload.get("duration_ms"))
    status = str(payload.get("status") or "").strip()
    metadata = str(payload.get("metadata") or "").strip()
    if category:
        parts.append(f"category={category}")
    if operation:
        parts.append(f"operation={operation}")
    if duration != "not available yet":
        parts.append(f"duration={duration}")
    if status:
        parts.append(f"status={status}")
    if metadata:
        parts.append(f"metadata={metadata[:80]}")
    return "; ".join(parts) or "not measured yet"


def _is_positive_number(value: object) -> bool:
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def _severity_from_runtime(snapshot: dict[str, Any]) -> Severity:
    if bool(snapshot.get("ready")):
        return "ok"
    if bool(snapshot.get("degraded")):
        return "warning"
    state = str(snapshot.get("lifecycle_state") or "").lower()
    return "error" if state in {"failed", "stopped"} else "unknown"


def _severity_from_llm_state(state: object) -> Severity:
    normalized = str(state or "").strip().lower()
    if normalized == "ready":
        return "ok"
    if normalized in {"disabled", "not available yet"}:
        return "unknown"
    if normalized in {"backend_missing", "model_missing", "failed"}:
        return "error"
    return "warning"


def _severity_from_activity(activity: object) -> Severity:
    normalized = str(activity or "").strip().lower()
    if "error" in normalized or "degraded" in normalized:
        return "error"
    if normalized in {"unknown"}:
        return "unknown"
    return "ok"


def _stringify(value: object) -> str:
    if value is None:
        return "not available yet"
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    text = str(value).strip()
    return text if text else "not available yet"


__all__ = ["FeedbackCenterSnapshotBuilder", "build_feedback_center_snapshot"]
