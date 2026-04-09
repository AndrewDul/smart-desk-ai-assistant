from __future__ import annotations

import queue
import time

import numpy as np

from .audio_runtime import OpenWakeWordGateAudioRuntime
from .helpers import LOGGER
from .scoring import OpenWakeWordGateScoring


class OpenWakeWordGateListener(
    OpenWakeWordGateAudioRuntime,
    OpenWakeWordGateScoring,
):
    """Wake listening loop and acceptance logic."""

    _MIN_VOICED_FRAMES_FOR_DIRECT_ACCEPT: int
    _MIN_VOICED_FRAMES_FOR_STABLE_ACCEPT: int
    _QUEUE_GET_TIMEOUT_SECONDS: float

    debug: bool
    input_sample_rate: int
    activation_cooldown_seconds: float
    block_release_settle_seconds: float
    energy_rms_threshold: float
    threshold: float
    trigger_level: int
    min_frames_before_accept: int
    direct_accept_threshold: float
    direct_accept_support_floor: float
    relaxed_hit_floor: float
    model_frame_samples: int
    frame_hop_samples: int
    _last_detection_monotonic: float
    _resampled_buffer: np.ndarray

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        effective_debug = bool(debug or self.debug)

        if not ignore_audio_block and self._input_blocked_by_assistant_output():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        if not ignore_audio_block and self._recently_unblocked():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        if self._in_activation_cooldown():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        try:
            self._ensure_stream_open()
        except Exception as error:
            LOGGER.error("Failed to start wake input stream: %s", error)
            self._close_stream()
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        self._clear_audio_queue()
        self._reset_runtime_state()

        started_at = time.monotonic()
        consecutive_hits = 0
        best_raw_score = 0.0
        best_smoothed_score = 0.0
        evaluated_frames = 0
        skipped_low_energy_frames = 0
        voiced_frames = 0

        while time.monotonic() - started_at <= float(timeout):
            if not ignore_audio_block and self._input_blocked_by_assistant_output():
                self._clear_audio_queue()
                self._reset_runtime_state()
                return None

            try:
                chunk = self.audio_queue.get(timeout=self._QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue
            except Exception as error:
                LOGGER.warning("Wake queue read error: %s", error)
                self._close_stream()
                self._clear_audio_queue()
                self._reset_runtime_state()
                return None

            pcm16 = np.asarray(chunk).astype(np.int16, copy=False)
            pcm16 = self._resample_to_16k(pcm16, self.input_sample_rate)
            if pcm16.size == 0:
                continue

            self._resampled_buffer = np.concatenate((self._resampled_buffer, pcm16))

            while len(self._resampled_buffer) >= self.model_frame_samples:
                frame = self._resampled_buffer[: self.model_frame_samples]
                self._resampled_buffer = self._resampled_buffer[self.frame_hop_samples :]

                if not self._frame_has_enough_energy(frame):
                    skipped_low_energy_frames += 1
                    consecutive_hits = max(0, consecutive_hits - 1)
                    self._soft_decay_state()
                    continue

                voiced_frames += 1

                try:
                    raw_prediction = self.model.predict(frame)
                except Exception as error:
                    LOGGER.warning("Wake model prediction failed: %s", error)
                    self._close_stream()
                    self._clear_audio_queue()
                    self._reset_runtime_state()
                    return None

                raw_score = self._extract_score(raw_prediction)
                smoothed_score = self._smoothed_score(raw_score)

                evaluated_frames += 1
                best_raw_score = max(best_raw_score, raw_score)
                best_smoothed_score = max(best_smoothed_score, smoothed_score)

                if smoothed_score >= self.threshold:
                    consecutive_hits += 1
                elif raw_score >= self.relaxed_hit_floor:
                    consecutive_hits = max(1, consecutive_hits)
                else:
                    consecutive_hits = max(0, consecutive_hits - 1)

                if effective_debug and self._should_print_debug():
                    print(
                        "OpenWakeWord "
                        f"raw={raw_score:.3f} smooth={smoothed_score:.3f} "
                        f"hits={consecutive_hits} eval={evaluated_frames} "
                        f"skip={skipped_low_energy_frames} voiced={voiced_frames}"
                    )

                strong_direct_accept = (
                    raw_score >= self.direct_accept_threshold
                    and smoothed_score >= self.direct_accept_support_floor
                    and voiced_frames >= self._MIN_VOICED_FRAMES_FOR_DIRECT_ACCEPT
                )

                stable_accept = (
                    smoothed_score >= self.threshold
                    and consecutive_hits >= self.min_frames_before_accept
                    and voiced_frames >= self._MIN_VOICED_FRAMES_FOR_STABLE_ACCEPT
                )

                if strong_direct_accept or stable_accept:
                    self._last_detection_monotonic = time.monotonic()
                    LOGGER.info(
                        "OpenWakeWord wake accepted: raw_score=%.3f, smooth_score=%.3f, "
                        "best_raw=%.3f, best_smooth=%.3f, evaluated_frames=%s, "
                        "skipped_low_energy_frames=%s, voiced_frames=%s, accept_path=%s",
                        raw_score,
                        smoothed_score,
                        best_raw_score,
                        best_smoothed_score,
                        evaluated_frames,
                        skipped_low_energy_frames,
                        voiced_frames,
                        "direct" if strong_direct_accept else "stable",
                    )
                    self._clear_audio_queue()
                    self._reset_runtime_state()
                    return "nexa"

        if effective_debug:
            print(
                "OpenWakeWord "
                f"best_raw={best_raw_score:.3f} best_smooth={best_smoothed_score:.3f} "
                f"eval={evaluated_frames} skip={skipped_low_energy_frames} voiced={voiced_frames}"
            )

        self._clear_audio_queue()
        self._reset_runtime_state()
        return None


__all__ = ["OpenWakeWordGateListener"]