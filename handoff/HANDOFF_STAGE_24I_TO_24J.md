# NEXA Voice Engine v2 — handoff Stage 24I to Stage 24J

## Current status

We are continuing NEXA Voice Engine v2 inside the same ChatGPT project.

The current completed stage is Stage 24I.

Stage 24I passed repository tests and Raspberry Pi hardware validation.

The next stage is:

Stage 24J — FasterWhisper callback tap source audit.

## Product direction

NEXA is a premium, compact, local-first AI assistant / AI robot on Raspberry Pi 5 16GB + Raspberry Pi AI HAT+ 2, DSI 8" 1280x800 display, camera, local voice pipeline, local vision and future mobility.

Treat NEXA as a serious premium product, not a demo or toy.

## Language / coding rules

Respond in Polish.

Code, comments in code, file names, paths, classes, functions, terminal commands and commit messages must be in English.

Do not use canvas.
Do not provide ZIPs/links instead of code.
Always give exact file path.
For small/medium files give full-file replacement.
For large files give exact find/replace patches.
Always mark: new file / existing file / full-file replacement / find/replace patch / deleted file.

After every larger stage provide:
- files changed,
- new files,
- deleted files,
- config changes,
- tests to run,
- cleanup,
- docs/architecture_notes.md entry,
- commit message only after green tests.

Do not leave legacy trash without a removal plan.
Do not break wake word, audio input, FasterWhisper, TTS or Visual Shell.
Do not take over production runtime blindly.
Audit files before patching.
Do not guess method names.

## Target Voice Engine v2 architecture

Wake word
→ RealtimeAudioBus
→ Silero VAD ONNX endpointing
→ Vosk command recognizer PL/EN
→ CommandIntentResolver
→ fast action

Fallback only if needed:
→ FasterWhisper
→ router / LLM / conversation
→ Piper TTS

Important:
FasterWhisper is not the fast-command recognizer.
The current FasterWhisper callback tap is only used as an existing microphone callback to mirror copied PCM into RealtimeAudioBus without starting a second microphone stream.

## Safe config must remain default

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false

Do not proceed to production takeover.
Do not prevent FasterWhisper.
Do not execute pre-STT actions.
Do not add Vosk yet.
Do not use FasterWhisper as fast-command recognizer.

## Completed stages summary

Stage 0B — migration gate:
- Voice Engine v2 disabled by default.
- Legacy runtime remains primary.

Stage 1 — RealtimeAudioBus foundation:
- modules/devices/audio/realtime/
- AudioFrame, AudioRingBuffer, AudioBus, AudioBusSubscription, AudioDeviceConfig, AudioCaptureWorker.

Stage 2 — VAD endpointing foundation:
- modules/devices/audio/vad/
- VadDecision, VadEvent, VadEventType, VadEngine, SileroVadEngine, EndpointingPolicy, EndpointingPolicyConfig.

Stage 3 — bilingual command recognizer grammar:
- modules/devices/audio/command_asr/
- PL/EN command grammar, Vosk shell, recovery variants.

Stage 4 — CommandIntentResolver:
- modules/core/command_intents/
- Deterministic resolver for visual shell/system intents.

Stage 5 — Voice Engine v2 pipeline contract:
- modules/core/voice_engine/
- command-first contract and fallback pipeline.

Stage 6 — runtime integration adapter:
- modules/runtime/voice_engine_v2/
- runtime bundle, builder mixin, metadata integration.

Stage 7 — visual-action-first executor:
- modules/core/voice_engine/execution/
- visual commands can execute before optional TTS.

Stage 8 — benchmarks:
- benchmarks/voice/
- deterministic command path around 50 ms in tests.

Stage 9–20C:
- shadow mode, runtime candidate adapter, telemetry and validators.
- only assistant.identity and system.current_time accepted as guarded runtime candidates in tests.
- all disabled again after hardware smoke.

Stage 21A–21C:
- pre-STT shadow hook before FasterWhisper.
- observe-only.
- hardware validation passed with audio_bus_unavailable_observe_only.
- no actions, no STT prevention.

Stage 22A–22C:
- RealtimeAudioBus pre-STT source probe.
- hardware confirmed active runtime did not expose bus initially.
- audit confirmed not to start a second microphone stream.

Stage 23A:
- FasterWhisper callback RealtimeAudioBus shadow tap.
- existing FasterWhisper callback copies mono PCM into AudioBus when guarded flag enabled.
- no second microphone owner.
- disabled by default.

Stage 23B:
- safety switch and hardware validation for audio bus tap.
- hardware result:
  audio_bus_present=true
  source=runtime.metadata.realtime_audio_bus
  frame_count=46
  duration_seconds=2.944
  snapshot_byte_count=6144
  probe_error=""
  legacy_runtime_primary=true
  action_executed=false
  full_stt_prevented=false

Stage 24A:
- Silero VAD shadow observer over RealtimeAudioBus.
- file:
  modules/runtime/voice_engine_v2/vad_shadow.py
- observe-only.

Stage 24B:
- safety switch and validator for VAD shadow.
- files:
  scripts/set_voice_engine_v2_vad_shadow.py
  scripts/validate_voice_engine_v2_vad_shadow_log.py
- hardware passed, but no events emitted.

Stage 24C:
- added VAD score diagnostics.
- validator supports:
  --require-score-diagnostics
- hardware passed but max_speech_score=0.0.
- conclusion: RealtimeAudioBus works, VAD sees audio, but score provider was wrong.

Stage 24D / 24D.1:
- fixed Silero frame-score provider.
- replaced get_speech_timestamps usage with direct Silero ONNX model probability scoring.
- 16 kHz uses 512-sample windows.
- 8 kHz uses 256-sample windows.
- tensor input fix added.
- hardware passed:
  max_speech_score≈0.99999
  speech_started emitted
  speech_ended emitted
  unsafe records all 0.

Stage 24E:
- added timing diagnostics:
  observation_started_monotonic
  observation_completed_monotonic
  observation_duration_ms
  first_frame_timestamp_monotonic
  last_frame_timestamp_monotonic
  last_frame_end_timestamp_monotonic
  last_frame_age_ms
  audio_window_duration_ms
  latest_speech_started_lag_ms
  latest_speech_ended_lag_ms
  latest_speech_end_to_observe_ms
- validator supports:
  --require-timing-diagnostics
- hardware passed, but showed ~4–5s delay:
  max_last_frame_age_ms≈4216ms
  max_speech_end_to_observe_ms≈4851ms.

Stage 24F:
- added cadence/backlog diagnostics:
  audio_bus_latest_sequence
  audio_bus_frame_count
  audio_bus_duration_seconds
  subscription_next_sequence_before
  subscription_next_sequence_after
  subscription_backlog_frames
  stale_audio_threshold_ms
  stale_audio_observed
  cadence_diagnostic_reason
- hardware proved current pre-STT observer often reads stale audio backlog:
  stale_audio_records=4
  max_subscription_backlog_frames=205
  stale_audio_backlog_observed=4
- conclusion: issue is observer hook/cadence, not Silero or AudioBus.

Stage 24G:
- added observe-only VAD timing bridge:
  modules/runtime/voice_engine_v2/vad_timing_bridge.py
  scripts/set_voice_engine_v2_vad_timing_bridge.py
  tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
  tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py
- bridge arms dedicated subscription before legacy capture and observes after capture.
- no second microphone stream.
- no VAD inference inside audio callback.
- hardware passed:
  stale_audio_records=0
  fresh_audio_backlog_observed=4
  max_last_frame_age_ms≈305ms
- but no VAD events:
  speech_frame_records=0
  max_speech_score≈0.34.

Stage 24H:
- added score profile diagnostics:
  score_profile_sample_count
  score_profile_first_scores
  score_profile_middle_scores
  score_profile_last_scores
  score_profile_peak_score
  score_profile_peak_index
  score_profile_peak_sequence
  score_profile_peak_position_ratio
  score_profile_peak_bucket
  score_profile_peak_frame_source
  score_profile_peak_frame_age_ms
  frame_source_counts
- validator supports:
  --require-score-profile-diagnostics
- hardware passed.
- bridge reads fresh frames from faster_whisper_callback_shadow_tap, but score remains low:
  max_score_profile_peak_score≈0.047
  speech_frame_records=0
  events=0.

Stage 24I:
- added PCM quality diagnostics:
  pcm_profile_frame_count
  pcm_profile_sample_width_bytes
  pcm_profile_total_byte_count
  pcm_profile_total_sample_count
  pcm_profile_rms
  pcm_profile_mean_abs
  pcm_profile_peak_abs
  pcm_profile_zero_ratio
  pcm_profile_near_zero_ratio
  pcm_profile_clipping_ratio
  pcm_profile_signal_level
  pcm_profile_first_frame_rms
  pcm_profile_first_frame_peak_abs
  pcm_profile_middle_frame_rms
  pcm_profile_middle_frame_peak_abs
  pcm_profile_last_frame_rms
  pcm_profile_last_frame_peak_abs
  pcm_profile_peak_frame_index
  pcm_profile_peak_frame_sequence
  pcm_profile_peak_frame_source
  pcm_profile_peak_frame_rms
  pcm_profile_peak_frame_peak_abs
  pcm_profile_peak_frame_zero_ratio
  pcm_profile_peak_frame_age_ms
- validator supports:
  --require-pcm-profile-diagnostics
- hardware passed:
  accepted=true
  pcm_profile_diagnostics_records=5
  stale_audio_records=0
  fresh_audio_backlog_observed=5
  max_score_profile_peak_score=0.2458934485912323
  max_pcm_profile_rms=0.000596
  max_pcm_profile_peak_abs=0.004517
  max_pcm_profile_mean_abs=0.000409
  max_pcm_profile_near_zero_ratio=0.999512
  pcm_profile_signal_levels:
    near_silent=5
  unsafe_action_records=0
  unsafe_full_stt_records=0
  unsafe_takeover_records=0
  issues=[]
- conclusion:
  bridge receives fresh frames, but they are near-silent.
  Problem is not Silero threshold, VAD policy, AudioBus subscription, or stale backlog.
  Problem is likely what _publish_realtime_audio_bus_shadow_tap publishes, its PCM scaling/conversion, or capture window/tail segment.

## Latest Stage 24I evidence

Legacy STT heard real commands:
- What is your name?
- What time is it?
- Introduce yourself.
- Exit.

But VAD timing bridge PCM profile showed:
- pcm_signal_level=near_silent
- pcm_rms around 0.00029–0.000596
- pcm_peak_abs around 0.00116–0.004517
- pcm_near_zero_ratio around 0.917–0.999
- events=0

Therefore do not lower VAD threshold as workaround.

## Next stage

Stage 24J — FasterWhisper callback tap source audit.

Goal:
Inspect real source code for _publish_realtime_audio_bus_shadow_tap(...) and determine exactly what PCM object is being published into RealtimeAudioBus.

Must inspect files before patching.

Likely files to inspect:
- modules/devices/audio/input/capture_adapters.py
- modules/devices/audio/input/*faster* or related capture mixin files
- modules/runtime/main_loop/active_window.py
- modules/runtime/voice_engine_v2/vad_timing_bridge.py
- modules/runtime/voice_engine_v2/vad_shadow.py
- modules/devices/audio/realtime/audio_bus.py
- modules/devices/audio/realtime/audio_frame.py
- tests related to FasterWhisper audio bus tap

Stage 24J should answer:
- what variable is passed into _publish_realtime_audio_bus_shadow_tap(...)
- whether it is int16 PCM, float PCM, normalized data, tail buffer, or already post-processed silence,
- whether timestamps are real capture time or publish time,
- whether callback is called during speech or only after endpointing,
- whether byte count/sample count match expected speech window,
- whether the tap is publishing the same data that FasterWhisper uses,
- whether the tap should publish earlier/fuller command-window PCM into RealtimeAudioBus.

Allowed Stage 24J patch:
- small guarded diagnostic patch only,
- observe-only,
- no production takeover,
- no action execution,
- no Vosk,
- no FasterWhisper prevention,
- no second microphone stream.

Do not change VAD threshold.
Do not start another microphone stream.
Do not move assistant logic into Godot.
Do not touch TTS/Visual Shell/wake unless audit proves directly necessary.

## Stage 24J recommended approach

1. Inspect source files first.
2. Find exact _publish_realtime_audio_bus_shadow_tap(...) method.
3. Inspect the callback that calls it.
4. Inspect data types and conversions.
5. Add minimal diagnostics around the tap:
   - input type,
   - input dtype if numpy,
   - input shape/length,
   - min/max,
   - RMS/peak before conversion,
   - output PCM byte count,
   - output sample count,
   - output RMS/peak after conversion,
   - timestamp used,
   - publish source,
   - whether callback frame is all/near zero,
   - whether callback happens before/after transcript.
6. Add validator support if needed.
7. Run tests.
8. Hardware validate.
9. Keep safe flags disabled after run.

## Important recent test commands that passed

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py

pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/test_core_assistant_import.py

## Cleanup reminders

Before commit or next hardware run:
find config -maxdepth 1 -type f -name "settings.json.bak-*" -delete
find modules tests scripts -type d -name "__pycache__" -prune -exec rm -rf {} +
find modules tests scripts -type f -name "*.pyc" -delete

Check safe config after hardware:
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false

## Commit status

If Stage 24I architecture note was added and all tests passed, commit message can be:

test(voice-engine): add pcm diagnostics for vad bridge

If it was not committed yet, commit before Stage 24J or mention this to the new window.
