# NeXa Raspberry Pi premium validation

This runbook defines the repeatable hardware validation flow for NeXa after boot acceptance and benchmark segmentation are already in place.

## 1. Preconditions

- Raspberry Pi boot acceptance passes or degraded mode is explicitly understood
- Hailo / hailo-ollama backend is reachable on the configured local endpoint
- the full regression suite is green
- benchmark storage path is writable

## 2. Print the validation flow

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/print_premium_validation_flow.py
```
Use that output as the canonical operator flow on Raspberry Pi.

3. Reset the benchmark window
cp var/data/turn_benchmarks.json var/data/turn_benchmarks.backup.json
python - <<'PY'
import json
from pathlib import Path

path = Path('var/data/turn_benchmarks.json')
payload = {'version': 1, 'updated_at_iso': '', 'samples': [], 'summary': {}}
path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(f'reset: {path}')
PY
4. Capture scenarios in order
Stage A — Voice and built-in skills

Goal:

populate wake, STT, reply start, and deterministic skill latency

Recommended prompts:

What time is it
What is today's date
Introduce yourself
Help me
Set timer for two minutes
Stop timer
Start focus mode for five minutes
Stop focus mode
Stage B — Short LLM streaming

Goal:

validate first chunk and early spoken playback for open questions

Recommended prompts:

Explain what a black hole is in simple terms
Compare Python and JavaScript in a few sentences
Explain overfitting in machine learning
What is event-driven architecture
Explain the difference between RAM and storage
Stage C — Long LLM, interruption, reminders

Goal:

stress long-turn response flow
verify interruption and follow-up continuity
verify reminder correctness

Recommended prompts:

Tell me a short story about Mars colonization
Explain how neural networks learn, step by step
Give me a detailed comparison of Python, Rust, and Go for backend systems
Interrupt NeXa while it is speaking and ask a new question
Set a reminder for one minute and wait for the trigger

### 5. Re-run the benchmark gate
python scripts/check_turn_benchmark_thresholds.py

Interpretation:

voice.* failures mean the wake / STT / response-start path is still too slow
skill.* failures mean deterministic commands are not yet premium-fast
llm.avg-first-chunk-ms failing points to model-side generation start
llm.avg-response-first-audio-ms failing while first chunk passes points to post-LLM handoff
llm.streaming-ratio failing means not enough LLM turns are being emitted through live streaming

### 6. Release evidence

Capture and save:

output of python scripts/check_turn_benchmark_thresholds.py
output of sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal
any screenshots or logs from interruption / reminder scenarios

### 7. Definition of pass for Stage 10.3

Stage 10.3 is complete when:

the operator has a repeatable Raspberry Pi validation flow
the scenario order is documented and scriptable
benchmark evidence can be collected intentionally for voice, skill, and LLM paths
the team can identify the slow segment without manual guesswork

