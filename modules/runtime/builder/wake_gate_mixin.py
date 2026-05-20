from __future__ import annotations

import os

from modules.runtime.contracts import RuntimeBackendStatus, SpeechInputBackend, WakeGateBackend
from modules.shared.logging.logger import get_logger

from .fallbacks import NullWakeGate
from .wake_gate import CompatibilityWakeGate

LOGGER = get_logger(__name__)


def _strict_real_wake_gate_required() -> bool:
    return str(os.environ.get("NEXA_REQUIRE_REAL_WAKE_GATE", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "run",
    }


def _raise_if_strict_real_wake_gate_required(detail: str) -> None:
    if _strict_real_wake_gate_required():
        raise RuntimeError(
            "A real wake-word gate is required for this runtime, but NeXa would use "
            f"developer text/compatibility wake mode. {detail}"
        )


class RuntimeBuilderWakeGateMixin:
    """
    Build the wake gate backend with compatibility fallbacks.
    """

    def _build_wake_gate(
        self,
        config: dict[str, object],
        *,
        voice_input: SpeechInputBackend,
        voice_input_status: RuntimeBackendStatus,
    ) -> tuple[WakeGateBackend | None, RuntimeBackendStatus]:
        if hasattr(voice_input, "listen_for_wake_phrase"):
            class_name = voice_input.__class__.__name__.lower()
            if "textinput" in class_name:
                _raise_if_strict_real_wake_gate_required(
                    "voice_input selected the TextInput wake backend."
                )
                return (
                    voice_input,  # type: ignore[return-value]
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="text_input",
                        requested_backend="text_input",
                        runtime_mode="developer_text_input",
                        capabilities=("listen_for_wake_phrase",),
                        detail="Wake gate handled by text input backend.",
                    ),
                )

        if not bool(config.get("enabled", True)):
            _raise_if_strict_real_wake_gate_required(
                "voice_input.enabled is false, so wake gate is disabled."
            )
            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="disabled",
                    requested_backend="disabled",
                    runtime_mode="disabled",
                    capabilities=(),
                    detail="Wake gate disabled because voice input is disabled.",
                ),
            )

        engine = str(config.get("wake_engine", "openwakeword")).strip().lower()
        if engine in {"off", "none", "disabled"}:
            _raise_if_strict_real_wake_gate_required(
                f"wake_engine is '{engine}'."
            )
            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="disabled",
                    requested_backend=engine,
                    runtime_mode="disabled",
                    capabilities=(),
                    detail="Wake gate disabled in config.",
                ),
            )

        single_capture_mode = self._single_capture_mode_enabled(config)
        prefer_dedicated_gate = bool(config.get("wake_prefer_dedicated_gate", False))
        wake_alsa_device = self._configured_wake_alsa_device(config)
        config_route_message = f"[wake-route] config_wake_alsa_device={wake_alsa_device!r}"
        print(config_route_message, flush=True)
        LOGGER.warning(config_route_message)
        force_dedicated_for_wake_alsa = engine == "openwakeword" and wake_alsa_device is not None
        if force_dedicated_for_wake_alsa and single_capture_mode and not prefer_dedicated_gate:
            route_message = (
                "[wake-route] selected_wake_backend=dedicated_openwakeword "
                "wake_alsa_device_active=true "
                f"wake_input_device={wake_alsa_device!r} "
                "reason='voice_input.wake_alsa_device requires arecord-backed wake capture'"
            )
            print(route_message, flush=True)
            LOGGER.warning(route_message)

        if (
            single_capture_mode
            and bool(voice_input_status.ok)
            and not prefer_dedicated_gate
            and not force_dedicated_for_wake_alsa
        ):
            _raise_if_strict_real_wake_gate_required(
                "wake_prefer_dedicated_gate is false, so compatibility wake would be used."
            )
            _raise_if_strict_real_wake_gate_required(
                f"Unsupported wake engine '{engine}'."
            )
            compatibility_gate = CompatibilityWakeGate(voice_input)
            wake_input_device = self._wake_input_device_label(compatibility_gate, voice_input)
            route_message = (
                "[wake-route] selected_wake_backend=compatibility_voice_input "
                f"wake_alsa_device_active=false wake_input_device={wake_input_device!r}"
            )
            print(route_message, flush=True)
            LOGGER.warning(route_message)
            return (
                compatibility_gate,
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="compatibility_voice_input",
                    requested_backend=engine,
                    runtime_mode="single_capture_compatibility",
                    capabilities=("listen_for_wake_phrase",),
                    detail=(
                        "Wake gate reuses the main voice input backend in single-capture mode. "
                        f"Wake input device/path: {wake_input_device}."
                    ),
                    metadata={
                        "selected_wake_backend": "compatibility_voice_input",
                        "wake_alsa_device_active": False,
                        "wake_alsa_device": "",
                        "wake_input_device": wake_input_device,
                    },
                ),
            )

        try:
            if engine == "openwakeword":
                backend_class = self._import_symbol(
                    "modules.devices.audio.input.wake.openwakeword_gate",
                    "OpenWakeWordGate",
                )
                backend = backend_class(
                    model_path=config.get("wake_model_path", "models/wake/nexa.onnx"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    alsa_device=wake_alsa_device,
                    threshold=float(config.get("wake_threshold", 0.50)),
                    trigger_level=int(config.get("wake_trigger_level", 2)),
                    block_ms=int(config.get("wake_block_ms", 80)),
                    vad_threshold=float(config.get("wake_vad_threshold", 0.0)),
                    enable_speex_noise_suppression=bool(
                        config.get("wake_enable_speex_noise_suppression", False)
                    ),
                    activation_cooldown_seconds=float(
                        config.get("wake_activation_cooldown_seconds", 1.25)
                    ),
                    block_release_settle_seconds=float(
                        config.get("wake_block_release_settle_seconds", 0.18)
                    ),
                    energy_rms_threshold=float(config.get("wake_energy_rms_threshold", 0.0085)),
                    score_smoothing_window=int(config.get("wake_score_smoothing_window", 3)),
                    wake_channel_mode=str(config.get("wake_channel_mode", "mono_mix")),
                    wake_channel_index=config.get("wake_channel_index"),
                    debug=bool(config.get("wake_debug", False)),
                )
                wake_input_device = self._wake_input_device_label(backend)
                route_message = (
                    "[wake-route] selected_wake_backend=dedicated_openwakeword "
                    f"wake_alsa_device_active={str(wake_alsa_device is not None).lower()} "
                    f"wake_input_device={wake_input_device!r}"
                )
                print(route_message, flush=True)
                LOGGER.warning(route_message)
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="openwakeword",
                        requested_backend="openwakeword",
                        runtime_mode="dedicated_wake_gate",
                        capabilities=("listen_for_wake_phrase",),
                        detail=(
                            "OpenWakeWord wake gate loaded successfully. "
                            f"Selected wake backend: dedicated_openwakeword. "
                            f"wake_alsa_device_active={wake_alsa_device is not None}. "
                            f"Wake input device/path: {wake_input_device}."
                        ),
                        metadata={
                            "selected_wake_backend": "dedicated_openwakeword",
                            "wake_alsa_device_active": wake_alsa_device is not None,
                            "wake_alsa_device": wake_alsa_device or "",
                            "wake_input_device": wake_input_device,
                        },
                    ),
                )

            compatibility_gate = CompatibilityWakeGate(voice_input)
            wake_input_device = self._wake_input_device_label(compatibility_gate, voice_input)
            route_message = (
                "[wake-route] selected_wake_backend=compatibility_voice_input "
                f"wake_alsa_device_active=false wake_input_device={wake_input_device!r}"
            )
            print(route_message, flush=True)
            LOGGER.warning(route_message)
            return (
                compatibility_gate,
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="compatibility_voice_input",
                    requested_backend=engine,
                    runtime_mode="single_capture_compatibility",
                    capabilities=("listen_for_wake_phrase",),
                    detail=(
                        f"Unsupported wake engine '{engine}'. "
                        "Using compatibility wake through the main voice input backend."
                    ),
                    metadata={
                        "selected_wake_backend": "compatibility_voice_input",
                        "wake_alsa_device_active": False,
                        "wake_alsa_device": "",
                        "wake_input_device": wake_input_device,
                    },
                    fallback_used=True,
                ),
            )

        except Exception as error:
            if wake_alsa_device is not None:
                _raise_if_strict_real_wake_gate_required(
                    f"Wake gate backend '{engine}' failed while wake_alsa_device was set: {error}"
                )
                return (
                    NullWakeGate(),
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=False,
                        selected_backend="disabled",
                        requested_backend=engine,
                        runtime_mode="disabled",
                        capabilities=(),
                        detail=(
                            f"Wake gate backend '{engine}' failed while "
                            "voice_input.wake_alsa_device was set. Not falling back to "
                            "compatibility wake because that path does not use the forced "
                            f"ALSA arecord device. Error: {error}"
                        ),
                        fallback_used=True,
                        metadata={
                            "selected_wake_backend": "disabled",
                            "wake_alsa_device_active": True,
                            "wake_alsa_device": wake_alsa_device,
                            "wake_input_device": f"alsa:{wake_alsa_device}",
                        },
                    ),
                )
            if bool(voice_input_status.ok):
                _raise_if_strict_real_wake_gate_required(
                    f"Wake gate backend '{engine}' failed: {error}"
                )
                compatibility_gate = CompatibilityWakeGate(voice_input)
                wake_input_device = self._wake_input_device_label(compatibility_gate, voice_input)
                route_message = (
                    "[wake-route] selected_wake_backend=compatibility_voice_input "
                    f"wake_alsa_device_active=false wake_input_device={wake_input_device!r}"
                )
                print(route_message, flush=True)
                LOGGER.warning(route_message)
                return (
                    compatibility_gate,
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="compatibility_voice_input",
                        requested_backend=engine,
                        runtime_mode="single_capture_compatibility",
                        capabilities=("listen_for_wake_phrase",),
                        detail=(
                            f"Wake gate backend '{engine}' failed. "
                            "Using compatibility wake through the main voice input backend. "
                            f"Error: {error}"
                        ),
                        metadata={
                            "selected_wake_backend": "compatibility_voice_input",
                            "wake_alsa_device_active": False,
                            "wake_alsa_device": "",
                            "wake_input_device": wake_input_device,
                        },
                        fallback_used=True,
                    ),
                )

            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=False,
                    selected_backend="disabled",
                    requested_backend=engine,
                    runtime_mode="disabled",
                    capabilities=(),
                    detail=(
                        f"Wake gate backend '{engine}' failed and voice input is unavailable. "
                        f"Error: {error}"
                    ),
                    fallback_used=True,
                ),
            )

    @staticmethod
    def _configured_wake_alsa_device(config: dict[str, object]) -> str | None:
        raw_value = config.get("wake_alsa_device")
        value = str(raw_value).strip() if raw_value is not None else ""
        return value or None

    @staticmethod
    def _wake_input_device_label(*objects: object) -> str:
        for obj in objects:
            if obj is None:
                continue
            for attr in ("device", "device_name"):
                value = getattr(obj, attr, None)
                if value is not None and str(value).strip():
                    return str(value)
        return "unknown"


__all__ = ["RuntimeBuilderWakeGateMixin"]
