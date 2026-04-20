# NeXa premium release gate

This document defines the final decision gate for declaring NeXa premium-ready on Raspberry Pi.

## 1. Preconditions

Before running the release gate:

- the full regression suite is green
- strict boot acceptance passes
- the premium validation flow has been executed on Raspberry Pi
- the benchmark window contains enough fresh samples for voice, skill, and llm segments

## 2. Run the release gate

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/check_premium_release_gate.py
```
### 3. Required pass conditions

The release gate passes only when all of the following are true:

strict boot acceptance passes
segmented turn benchmark validation passes
benchmark window size meets the minimum release threshold
voice segment passes
skill segment passes
llm segment passes
runtime lifecycle state is ready
runtime startup mode is premium
primary_ready=true
premium_ready=true

### 4. Required release evidence

Save and archive:

output of python scripts/check_turn_benchmark_thresholds.py
output of python scripts/check_premium_release_gate.py
output of sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal
notes from interruption, follow-up, and reminder scenarios

### 5. Definition of blocked release

A release is blocked when any of the following still fails:

voice latency gates
skill latency gates
llm streaming or llm response-start gates
strict systemd boot acceptance
runtime premium-ready state

### 6. Decision rule
PREMIUM-READY means the release candidate is acceptable for premium validation sign-off.
BLOCKED means the current build is not ready and optimization work must continue.