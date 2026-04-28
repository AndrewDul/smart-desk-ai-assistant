# NEXA Voice Engine v2 — Handoff Stage 24Q to Stage 24R

Current completed stage:
Stage 24Q — CommandAudioSegment contract.

Important:
This project uses docs/architecture_notes.md as the active stage-by-stage architecture log.
Do not rely only on docs/architecture.md.

Safe default config:
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false

Current observe-only Voice Engine v2 chain:
capture-window PCM
→ RealtimeAudioBus
→ Silero VAD pre-transcription observer
→ endpointing_candidate
→ command_recognition_readiness
→ command_audio_segment contract
→ validators

Completed stages:
- Stage 24I/24J: diagnosed near-silent callback tap; do not lower Silero threshold.
- Stage 24K: added capture-window shadow tap; PCM is healthy.
- Stage 24L: published capture-window PCM before FasterWhisper transcription.
- Stage 24M: added pre-transcription VAD observer.
- Stage 24N: added structured VAD endpointing candidate.
- Stage 24O: added endpointing candidate validator.
- Stage 24P: added command recognition readiness gate.
- Stage 24Q: added command audio segment contract.

Stage 24Q added:
- modules/runtime/voice_engine_v2/command_audio_segment.py
- scripts/validate_voice_engine_v2_command_audio_segments.py
- tests/runtime/voice_engine_v2/test_command_audio_segment.py
- tests/scripts/test_validate_voice_engine_v2_command_audio_segments.py

Stage 24Q validation:
accepted=true
issues=[]
segment_records=6
segment_present_records=5
rejected_segment_records=1
segment_ready_for_command_recognizer=5
not_ready:not_ready:endpoint_detected=1
source=faster_whisper_capture_window_shadow_tap
publish_stage=before_transcription
max_audio_duration_ms=2068.0
max_audio_sample_count=33088
max_published_byte_count=66176
max_speech_score=0.9999922513961792
max_capture_finished_to_vad_observed_ms=228.085
max_capture_window_publish_to_vad_observed_ms=226.232
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0

The single rejected segment is acceptable because it represents an intermediate VAD state:
speech_not_ended_yet

Next stage:
Stage 24R — disabled command ASR adapter contract.

Stage 24R goal:
Add only disabled/observe-only command ASR contracts:
- CommandAsrRecognizer protocol
- CommandAsrResult
- CommandAsrCandidate
- NullCommandAsrRecognizer / DisabledCommandAsrRecognizer
- tests
- validator for safe disabled command ASR telemetry

Stage 24R must NOT:
- integrate active Vosk runtime
- execute commands
- prevent FasterWhisper
- bypass FasterWhisper
- start another microphone stream
- lower VAD threshold
- change wake word
- change TTS
- change Visual Shell
- enable voice_engine.command_first_enabled

Working rules:
Respond in Polish.
Code/comments/file paths/classes/functions/terminal commands/commit messages in English.
Always audit source files first.
No canvas.
No ZIPs as replacement for code.
No commit message before tests pass.
