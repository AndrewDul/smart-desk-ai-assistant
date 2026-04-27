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


## Validate pre-STT shadow telemetry

After a controlled hardware run, validate the telemetry log:

```bash
python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed
```
Expected result:

accepted=true
observed_records>=1

The validator fails if any record shows:

action_executed=true
full_stt_prevented=true
legacy_runtime_primary=false

For Stage 21C, accepted telemetry reasons are:

audio_bus_unavailable_observe_only
audio_bus_available_observe_only

audio_bus_unavailable_observe_only is expected until the realtime audio bus is wired into the active command window in shadow mode.


---

## Stage 22A realtime audio bus probe

Stage 22A adds an observe-only realtime audio bus probe to the pre-STT shadow telemetry.

The probe does not start capture, does not subscribe as a consumer, does not take microphone ownership and does not prevent FasterWhisper.

It records diagnostic fields such as:

```text
audio_bus_present
sample_rate
channels
sample_width_bytes
frame_count
duration_seconds
latest_sequence
snapshot_byte_count
source
probe_error
```

Expected current hardware result before the realtime bus is wired into the active command window:

audio_bus_present=false
reason=audio_bus_unavailable_observe_only

When a realtime audio bus becomes available in runtime metadata or on the assistant object, expected result becomes:

audio_bus_present=true
reason=audio_bus_available_observe_only

Both states are safe as long as:

legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false

---