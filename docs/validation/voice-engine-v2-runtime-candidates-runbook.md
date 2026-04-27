# Voice Engine v2 runtime candidates runbook

This runbook describes how to safely enable and disable the guarded Voice Engine v2 runtime-candidate path.

Runtime candidates are not the full Voice Engine v2 production runtime.

They are a controlled Stage 20A validation path for selected deterministic commands:

- `assistant.identity`
- `system.current_time`

The candidate path still starts after the legacy STT transcript exists, so it does not yet solve the main wake/capture/endpointing/FasterWhisper latency bottleneck.

## Safe default

Default state must remain:

```text
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
Check status
python scripts/set_voice_engine_v2_runtime_candidates.py --status

Expected safe status:

safe_to_enable_runtime_candidates=true
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
Enable runtime candidates
python scripts/set_voice_engine_v2_runtime_candidates.py --enable

The script creates a backup of config/settings.json before writing changes.

The script refuses to enable runtime candidates if:

voice_engine.enabled is not false
voice_engine.mode is not legacy
voice_engine.command_first_enabled is not false
voice_engine.fallback_to_legacy_enabled is not true
Supported Stage 20A candidates

Only these intents are supported:

assistant.identity
system.current_time

system.exit is intentionally not enabled as a runtime candidate in Stage 20A.

Controlled hardware test prompts

After enabling runtime candidates, start NEXA normally and test only these prompts first:

What is your name?
What time is it?

Expected behaviour:

NEXA still wakes and captures through the existing legacy runtime.
Voice Engine v2 may accept only allowlisted deterministic candidates.
The actual action is still executed by existing ActionFlow handlers.
No LLM should be used for those clear deterministic commands.
Anything uncertain must fall back to legacy.

Negative prompts for safety:

exit
show shell
So shall
Oka Shell

Expected behaviour:

exit must not be accepted as a Stage 20A runtime candidate.
ambiguous Visual Shell transcripts must not be treated as safe candidates.
legacy fallback remains available.
Disable immediately after test
python scripts/set_voice_engine_v2_runtime_candidates.py --disable

Confirm:

python scripts/set_voice_engine_v2_runtime_candidates.py --status

Expected:

voice_engine.runtime_candidates_enabled=false
Important limitation

Stage 20A does not yet fix the main latency problem.

The real low-latency architecture still requires moving command recognition before FasterWhisper:

realtime audio bus
→ VAD endpointing
→ command-first recognizer
→ deterministic intent resolver
→ fast action

---

# Testy do uruchomienia

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate

pytest -q tests/scripts/test_set_voice_engine_v2_runtime_candidates.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/command_asr
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice

Potem sprawdź realny status configu:

python scripts/set_voice_engine_v2_runtime_candidates.py --status

Oczekiwane teraz:

voice_engine.runtime_candidates_enabled=false
safe_to_enable_runtime_candidates=true
Cleanup

Na tym etapie:

Deleted files: none.

Nie usuwamy:

legacy runtime
shadow mode
FasterWhisper path
wake word path
TTS path
Visual Shell path

Sprawdź:

grep -R "runtime_candidates_enabled" -n modules tests scripts docs
grep -R "set_voice_engine_v2_runtime_candidates" -n scripts tests docs
grep -R "system.exit" -n scripts docs modules tests

Oczekiwane:

runtime_candidates_enabled jest tylko w config/settings/runtime-candidate testach i runtime settings,
system.exit nie jest w default runtime candidate allowlist,
script nie zmienia voice_engine.enabled, mode, command_first_enabled.