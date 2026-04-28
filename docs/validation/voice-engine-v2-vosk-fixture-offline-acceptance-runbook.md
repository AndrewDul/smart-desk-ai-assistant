# Voice Engine v2 - Offline Vosk Fixture Acceptance Runbook

## Status

Stage 24AI runbook.

This procedure validates the offline Vosk command fixture chain for NEXA Voice Engine v2.

This is an offline-only procedure.

It must not connect Vosk to live runtime.

It must not start a live microphone stream.

It must not execute commands.

It must not bypass FasterWhisper.

It must not change wake word, audio input, TTS, or Visual Shell behavior.

---

## Purpose

NEXA Voice Engine v2 is moving toward a command-first local voice pipeline:

```text
Wake word
-> RealtimeAudioBus
-> Silero VAD ONNX endpointing
-> Vosk command recognizer PL/EN
-> CommandIntentResolver
-> fast action
```

Fallback only when needed:

```text
FasterWhisper
-> router / LLM / conversation
-> Piper TTS
```

Before Vosk can be considered for any live observe-only shadow path, the offline fixture evidence must be repeatable and gated.

---

## Current offline fixture set

Expected fixture root:

```text
var/data/fixtures/voice_commands/
```

Expected fixtures:

```text
EN:
- en_show_desktop.wav
- en_hide_desktop.wav
- en_what_time_is_it.wav

PL:
- pl_pokaz_pulpit.wav
- pl_schowaj_pulpit.wav
- pl_ktora_godzina.wav
```

Expected phrases:

```text
EN:
- show desktop
- hide desktop
- what time is it

PL:
- pokaz pulpit
- schowaj pulpit
- ktora godzina
```

Expected command intents:

```text
show desktop        -> visual_shell.show_desktop
hide desktop        -> visual_shell.show_shell
what time is it     -> system.current_time
pokaz pulpit        -> visual_shell.show_desktop
schowaj pulpit      -> visual_shell.show_shell
ktora godzina       -> system.current_time
```

---

## Required local assets

The Vosk package and models are local Raspberry Pi runtime assets.

They must not be committed.

Expected local model paths:

```text
var/models/vosk/vosk-model-small-en-us-0.15
var/models/vosk/vosk-model-small-pl-0.22
```

Check:

```bash
test -d var/models/vosk/vosk-model-small-en-us-0.15 && echo "EN model present"
test -d var/models/vosk/vosk-model-small-pl-0.22 && echo "PL model present"
```

Expected:

```text
EN model present
PL model present
```

---

## Required safe config

The production runtime must remain safe by default.

Expected safe defaults:

```text
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false
voice_engine.command_asr_shadow_bridge_enabled=false
```

This runbook does not require changing these flags.

---

## Step 1 - activate project environment

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
```

---

## Step 2 - validate fixture inventory

```bash
python scripts/manage_voice_engine_v2_command_fixtures.py validate \
  --require-records \
  --require-language en \
  --require-language pl
```

Expected key result:

```text
accepted=true
fixture_records=6
language_counts.en=3
language_counts.pl=3
issues=[]
```

If this fails, do not continue.

Fix fixture import first.

Required WAV format:

```text
mono
16000 Hz
PCM16
duration <= 5000 ms
```

---

## Step 3 - run offline Vosk fixture matrix

```bash
python scripts/run_voice_engine_v2_vosk_fixture_matrix.py \
  --report-dir var/data/stage24ag_vosk_fixture_matrix \
  --summary-output-path var/data/stage24ag_vosk_fixture_matrix_summary.json \
  --require-language en \
  --require-language pl
```

Expected key result:

```text
accepted=true
total_items=6
accepted_items=6
failed_items=0
summary.accepted=true
summary.total_reports=6
summary.accepted_reports=6
summary.matched_reports=6
summary.language_match_records=6
summary.language_mismatch_records=0
summary.unsafe_flag_records=0
```

Expected safety fields:

```text
runtime_integration=false
command_execution_enabled=false
faster_whisper_bypass_enabled=false
microphone_stream_started=false
live_command_recognition_enabled=false
```

Notes:

- Vosk may print warnings for words missing in the small model vocabulary.
- Warnings alone do not fail the stage.
- JSON output and the quality gate result are the source of truth.

---

## Step 4 - run offline quality gate

```bash
python scripts/check_voice_engine_v2_vosk_fixture_matrix_quality.py \
  --summary-path var/data/stage24ag_vosk_fixture_matrix_summary.json \
  --require-language en \
  --require-language pl \
  --max-elapsed-ms 2000 \
  --output-path var/data/stage24ah_vosk_fixture_quality_gate.json
```

Expected key result:

```text
accepted=true
issues=[]
observed.total_items=6
observed.accepted_items=6
observed.failed_items=0
observed.total_reports=6
observed.accepted_reports=6
observed.matched_reports=6
observed.language_match_records=6
observed.language_mismatch_records=0
observed.unsafe_flag_records=0
observed.elapsed_ms.max <= 2000
```

Expected safety fields:

```text
runtime_integration=false
command_execution_enabled=false
faster_whisper_bypass_enabled=false
microphone_stream_started=false
live_command_recognition_enabled=false
```

Important:

The --max-elapsed-ms 2000 value validates offline Vosk fixture recognition elapsed time.

It is not the final speech-end-to-action latency benchmark.

The final premium target still requires later live pipeline metrics such as:

```text
speech_end_to_action_ms
endpoint_delay_ms
command_stt_ms
command_resolver_ms
action_dispatch_ms
fallback_used
fallback_reason
language_final
```

---

## Step 5 - run regression tests

```bash
pytest -q tests/runtime/voice_engine_v2/test_vosk_fixture_quality_gate.py
pytest -q tests/scripts/test_check_voice_engine_v2_vosk_fixture_matrix_quality.py
pytest -q tests/runtime/voice_engine_v2/test_vosk_fixture_matrix_runner.py
pytest -q tests/scripts/test_run_voice_engine_v2_vosk_fixture_matrix.py
pytest -q tests/runtime/voice_engine_v2/test_vosk_fixture_report_summary.py
pytest -q tests/scripts/test_summarize_voice_engine_v2_vosk_fixture_reports.py
pytest -q tests/runtime/voice_engine_v2/test_vosk_fixture_recognition_probe.py
pytest -q tests/scripts/test_probe_voice_engine_v2_vosk_fixture_recognition.py
pytest -q tests/test_core_assistant_import.py
```

Expected:

```text
all passed
```

---

## Step 6 - cleanup checks

```bash
git status --short

git check-ignore -v var/data/stage24ah_vosk_fixture_quality_gate.json
git check-ignore -v var/data/stage24ag_vosk_fixture_matrix_summary.json
git check-ignore -v var/data/stage24ag_vosk_fixture_matrix/en_show_desktop.json
git check-ignore -v var/data/fixtures/voice_commands/en/en_show_desktop.wav
git check-ignore -v var/models/vosk/vosk-model-small-en-us-0.15
git check-ignore -v var/models/vosk/vosk-model-small-pl-0.22
```

Expected:

```text
var/data/... files are ignored
var/models/... files are ignored
no WAV files are tracked
no Vosk models are tracked
no generated JSON reports are tracked
```

Allowed tracked files for Stage 24AI:

```text
A docs/validation/voice-engine-v2-vosk-fixture-offline-acceptance-runbook.md
A tests/docs/test_voice_engine_v2_vosk_fixture_offline_runbook.py
M docs/architecture_notes.md
```

---

## Failure handling

### Fixture inventory fails

Do not continue.

Fix fixture import first.

### Matrix fails

Inspect per-fixture reports under:

```text
var/data/stage24ag_vosk_fixture_matrix/
```

Common failure causes:

```text
model_path_missing
wav_path_missing
wav_not_valid_for_fixture_probe
command_match_missing
command_language_mismatch
```

Do not patch live runtime to fix fixture failures.

### Quality gate fails

Inspect:

```text
var/data/stage24ah_vosk_fixture_quality_gate.json
```

Do not continue toward live shadow work until:

```text
accepted=true
issues=[]
```

### Local reports accidentally appear in git status

Do not commit them.

Check .gitignore.

Expected ignored locations:

```text
var/data/
var/models/
```

---

## Non-negotiable safety rules

This offline runbook must not:

```text
execute commands
bypass FasterWhisper
start live Voice Engine v2 microphone recognition
change wake word
change audio input
change TTS
change Visual Shell
enable Voice Engine v2 runtime takeover
connect Vosk recognition to live runtime
```

---

## Acceptance criteria

Stage 24AI is accepted when:

```text
fixture inventory accepted=true
matrix accepted=true
quality gate accepted=true
issues=[]
tests passed
cleanup checks confirm generated assets are ignored
docs/architecture_notes.md updated
```

Only after that, the project may move to the next stage:

```text
Stage 24AJ - prepare observe-only live Vosk shadow contract
```

Stage 24AJ must still be disabled by default and must not execute commands.
