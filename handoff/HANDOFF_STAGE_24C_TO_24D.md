# NEXA Voice Engine v2 — Stage 24C to Stage 24D handoff

## Current project direction

NEXA Voice Engine v2 target architecture:

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

FasterWhisper is NOT the fast-command recognizer.
FasterWhisper currently only provides the existing microphone callback that mirrors copied PCM into RealtimeAudioBus.

## Safe default config

Keep default config safe:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false

## Completed stages relevant to Stage 24D

Stage 23B:
- FasterWhisper callback RealtimeAudioBus shadow tap validated on hardware.
- pre-STT probe saw:
  audio_bus_present=true
  source=runtime.metadata.realtime_audio_bus
  frame_count=46
  duration_seconds=2.944
  snapshot_byte_count=6144
  probe_error=""
- Safety:
  legacy_runtime_primary=true
  action_executed=false
  full_stt_prevented=false

Stage 24A:
- Added VAD shadow observer over RealtimeAudioBus.
- File:
  modules/runtime/voice_engine_v2/vad_shadow.py
- Config:
  voice_engine.vad_shadow_enabled=false
  voice_engine.vad_shadow_max_frames_per_observation=96
  voice_engine.vad_shadow_speech_threshold=0.5
  voice_engine.vad_shadow_min_speech_ms=120
  voice_engine.vad_shadow_min_silence_ms=250
- Observe-only.

Stage 24B:
- Added VAD shadow safety switch and validator.
- Files:
  scripts/set_voice_engine_v2_vad_shadow.py
  scripts/validate_voice_engine_v2_vad_shadow_log.py
- Hardware validation passed:
  pre_stt_shadow.accepted=true
  vad_shadow.accepted=true
  vad_shadow_records=5
  enabled_records=5
  observed_records=5
  audio_bus_present_records=5
  frames_processed_records=4
  total_frames_processed=184
  unsafe_action_records=0
  unsafe_full_stt_records=0
  unsafe_takeover_records=0
  issues=[]
- But:
  total_events_emitted=0
  event_types={}

Stage 24C:
- Added VAD score diagnostics.
- Validator now supports:
  --require-score-diagnostics
- Hardware validation passed:
  accepted=true
  diagnostics_records=5
  speech_score_records=4
  speech_frame_records=0
  silence_frame_records=4
  max_speech_score=0.0
  max_speech_frame_count=0
  max_silence_frame_count=46
  event_emission_reasons:
    no_new_audio_frames_observe_only=1
    all_scores_below_threshold:max=0.000:threshold=0.500=4
  unsafe_action_records=0
  unsafe_full_stt_records=0
  unsafe_takeover_records=0
  issues=[]

## Stage 24C conclusion

RealtimeAudioBus works.
VAD shadow sees audio.
VAD shadow processes frames.
Safety is clean.

But current SileroOnnxVadScoreProvider always returns score 0.0 on live hardware.

The problem is not AudioBus and not pre-STT hook.
The problem is the scoring method.

Current issue:
- SileroOnnxVadScoreProvider uses get_speech_timestamps(...) as if it were a per-frame score provider.
- That is not appropriate for frame-by-frame shadow endpointing.
- Stage 24D should replace this with direct Silero model probability scoring over valid 512-sample windows at 16 kHz.

## Next stage

Stage 24D — Silero frame-score provider fix.

Goal:
- Inspect actual current source first.
- Fix only the VAD score provider.
- Keep path observe-only.
- Do not run Vosk yet.
- Do not execute actions.
- Do not prevent FasterWhisper.
- Do not change wake word, TTS or Visual Shell.
- Do not start a second microphone stream.
- Do not enable production runtime takeover.

Expected Stage 24D outcome:
- Hardware VAD shadow telemetry should show non-zero speech_score_max during spoken commands.
- Ideally speech_frame_records > 0.
- Maybe speech_started/speech_ended events start appearing, but first goal is non-zero score diagnostics.

## Tests known to run

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_pre_stt_shadow.py
pytest -q tests/runtime/voice_engine_v2

pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/devices/audio/command_asr
pytest -q tests/scripts/test_set_voice_engine_v2_audio_bus_tap.py
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice

## Hardware validation pattern after Stage 24D tests pass

python scripts/set_voice_engine_v2_runtime_candidates.py --disable
python scripts/set_voice_engine_v2_vad_shadow.py --disable
python scripts/set_voice_engine_v2_audio_bus_tap.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable

python scripts/set_voice_engine_v2_pre_stt_shadow.py --enable
python scripts/set_voice_engine_v2_audio_bus_tap.py --enable
python scripts/set_voice_engine_v2_vad_shadow.py --enable

rm -f var/data/voice_engine_v2_pre_stt_shadow.jsonl
python main.py

Say:
NeXa, what is your name?
NeXa, what time is it?
NeXa, what is your name?
NeXa, exit.
Yes.

Then disable immediately:
python scripts/set_voice_engine_v2_vad_shadow.py --disable
python scripts/set_voice_engine_v2_audio_bus_tap.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable

Validate:
python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics
