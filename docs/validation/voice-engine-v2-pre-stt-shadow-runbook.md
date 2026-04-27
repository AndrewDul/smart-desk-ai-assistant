# Voice Engine v2 pre-STT shadow runbook

This runbook describes how to safely enable and disable the Stage 21B pre-STT shadow hook.

The pre-STT shadow hook runs before legacy full STT capture starts, but it is observation-only.

It must never:

- execute actions,
- prevent legacy FasterWhisper capture,
- take microphone ownership,
- route to LLM,
- change Visual Shell state.

## Safe default

Default state must remain:

```text
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
Check status
python scripts/set_voice_engine_v2_pre_stt_shadow.py --status

Expected safe status:

safe_to_enable_pre_stt_shadow=true
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
Enable pre-STT shadow
python scripts/set_voice_engine_v2_pre_stt_shadow.py --enable

The script creates a backup of config/settings.json before writing changes.

The script refuses to enable pre-STT shadow if:

voice_engine.enabled is not false
voice_engine.mode is not legacy
voice_engine.command_first_enabled is not false
voice_engine.fallback_to_legacy_enabled is not true
voice_engine.runtime_candidates_enabled is not false

The runtime_candidates_enabled=false requirement keeps Stage 21B isolated from the post-STT runtime candidate experiment.

Hardware smoke run

After enabling:

rm -f var/data/voice_engine_v2_pre_stt_shadow.jsonl
python main.py

Test one or two normal wake/command turns, for example:

What is your name?
What time is it?

Expected visible behaviour:

NEXA still uses legacy capture/FasterWhisper.
NEXA still responds normally.
No fast pre-STT action should happen yet.
No full STT capture should be skipped.

Expected telemetry:

var/data/voice_engine_v2_pre_stt_shadow.jsonl

Expected record values:

legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false
reason=audio_bus_unavailable_observe_only

The audio_bus_unavailable_observe_only reason is expected at Stage 21B because the production active command window has not yet been wired to a live realtime audio bus.

Inspect telemetry
tail -n 20 var/data/voice_engine_v2_pre_stt_shadow.jsonl

Every record must preserve:

action_executed=false
full_stt_prevented=false
legacy_runtime_primary=true
Disable after hardware test
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --status

Expected:

voice_engine.pre_stt_shadow_enabled=false
Important limitation

Stage 21B does not yet run command recognition before FasterWhisper.

It only proves that a safe pre-STT hook can run before legacy full STT starts.

The next architectural step is to attach a realtime audio bus source to this pre-STT hook in shadow mode only.


---

# 4. `docs/validation/voice-engine-v2-runtime-candidates-runbook.md`

**Existing file — append small cross-reference**

```markdown
## Related pre-STT shadow validation

The runtime candidate path validates post-STT deterministic command execution.

For the next migration step before FasterWhisper, use:

```text
docs/validation/voice-engine-v2-pre-stt-shadow-runbook.md

The pre-STT shadow path must be tested separately with runtime_candidates_enabled=false so the hardware run proves only the pre-STT observation hook.