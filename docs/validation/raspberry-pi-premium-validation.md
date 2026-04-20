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