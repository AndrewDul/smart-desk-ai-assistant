# NeXa Raspberry Pi — Useful Commands

This file collects the most useful operational commands for running, stopping, checking, and updating NeXa on Raspberry Pi.

## 1. How to stop NeXa

If NeXa started automatically through systemd:

```bash
sudo systemctl stop nexa.service
```

If you also want to stop the separate LLM backend service:

```bash
sudo systemctl stop nexa-llm.service
```

If NeXa was started manually in the foreground inside a terminal:

```bash
Ctrl + C
```

## 2. Start NeXa again

```bash
sudo systemctl start nexa.service
```

If your setup also uses the separate LLM service:
```bash
hailo-ollama
```

```bash
sudo systemctl start nexa-llm.service
```

## 3. Restart services

Restart only NeXa:

```bash
sudo systemctl restart nexa.service
```

Restart NeXa and LLM:

```bash
sudo systemctl restart nexa.service
sudo systemctl restart nexa-llm.service
```

## 4. Check service status

```bash
sudo systemctl status nexa.service --no-pager
```

```bash
sudo systemctl status nexa-llm.service --no-pager
```

## 5. Follow logs live

NeXa logs:

```bash
journalctl -u nexa.service -f
```

LLM logs:

```bash
journalctl -u nexa-llm.service -f
```

## 6. Show recent logs

NeXa:

```bash
journalctl -u nexa.service -n 80 --no-pager
```

LLM:

```bash
journalctl -u nexa-llm.service -n 80 --no-pager
```

## 7. Disable auto-start on boot

Disable only NeXa auto-start:

```bash
sudo systemctl disable nexa.service
```

Disable both NeXa and LLM auto-start:

```bash
sudo systemctl disable nexa.service
sudo systemctl disable nexa-llm.service
```

## 8. Enable auto-start on boot again

```bash
sudo systemctl enable nexa.service
```

```bash
sudo systemctl enable nexa-llm.service
```

## 9. Reload systemd after unit changes

```bash
sudo systemctl daemon-reload
```

## 10. Project root and virtual environment

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
```

## 11. Render systemd units

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/render_systemd_units.py
```

## 12. Install or update systemd units and start services

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/install_systemd_units.py --start
```

## 13. Uninstall systemd units

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/uninstall_systemd_units.py
```

## 14. Roll back systemd units from backup

Replace `/path/to/backup-dir` with the real backup directory returned by the install step.

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/rollback_systemd_units.py /path/to/backup-dir --start
```

## 15. Boot acceptance check

Strict premium check:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal
```

Relaxed degraded check:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --allow-degraded --show-journal
```

## 16. Run main regression tests

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
pytest -q
```

## 17. Useful benchmark-related scripts

Run premium validation capture:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/run_premium_validation_capture.py
```

Inspect turn benchmark samples:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/inspect_turn_benchmark_samples.py
```

Check benchmark thresholds:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/check_turn_benchmark_thresholds.py
```

Check premium release gate:

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/check_premium_release_gate.py
```

## 18. When to use which stop command

### Case A — NeXa booted automatically after Raspberry Pi start
Use:

```bash
sudo systemctl stop nexa.service
```

### Case B — NeXa was started from the terminal manually
Use:

```bash
Ctrl + C
```

### Case C — You want NeXa not to start automatically next boot
Use:

```bash
sudo systemctl disable nexa.service
```

## 19. Recommended quick recovery sequence

If NeXa behaves strangely after boot:

```bash
sudo systemctl stop nexa.service
sudo systemctl stop nexa-llm.service
sudo systemctl daemon-reload
sudo systemctl start nexa-llm.service
sudo systemctl start nexa.service
sudo systemctl status nexa.service --no-pager
```

## 20. Suggested repo location

If you want this file inside the project, save it as:

```text
docs/raspberry-pi-useful-commands.md
```
