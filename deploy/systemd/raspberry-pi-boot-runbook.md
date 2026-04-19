# NeXa Raspberry Pi boot runbook

This runbook is the operational baseline for installing, verifying, updating and recovering NeXa systemd services on Raspberry Pi.

## 1. Preconditions

- Raspberry Pi project root is available on disk
- Python virtual environment is ready
- `config/settings.json` is configured for the target device
- optional overrides were copied from `config/systemd/nexa.env.example` to `config/systemd/nexa.env`
- the local LLM backend configuration is already decided

## 2. Render units

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
python scripts/render_systemd_units.py
```

Expected result:

generated unit files appear under deploy/systemd/
unit names match the deployment section in config/settings.json

### 3. First install on Raspberry Pi

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/install_systemd_units.py --start
```

### Expected result:

units are copied into /etc/systemd/system
systemctl daemon-reload runs
units are enabled
units are restarted

### 4. Immediate verification after install
```bash
sudo systemctl status nexa.service --no-pager
sudo systemctl status nexa-llm.service --no-pager
```

If LLM service is not enabled in settings, only verify nexa.service.

### 5. Hardware boot acceptance

Strict premium check:
```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal
```

Relaxed check for temporary degraded validation:
```bash
sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --allow-degraded --show-journal
```

Expected strict premium result:

installed unit files exist
units are active and enabled
runtime status file exists
runtime lifecycle is ready
primary_ready=true
premium_ready=true
startup mode is premium

### 6. Logs

Application logs:
```bash
journalctl -u nexa.service -n 80 --no-pager
```
LLM logs:
```bash
journalctl -u nexa-llm.service -n 80 --no-pager
```
Follow live logs:
```bash
journalctl -u nexa.service -f
journalctl -u nexa-llm.service -f
```
### 7. Safe update flow

Before updating code:

pull or copy the new project snapshot
confirm settings are still correct
activate the virtual environment
run the full regression suite
```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
pytest -q
```
Then install updated units:
```bash
sudo .venv/bin/python scripts/install_systemd_units.py --start
```
If an existing unit file is being replaced, the install step creates a backup directory.

### 8. Rollback

Use the backup directory returned by the install step.
```bash
sudo .venv/bin/python scripts/rollback_systemd_units.py /path/to/backup-dir --start
```
After rollback, verify again:
```bash
sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal
```
### 9. Uninstall
```bash
sudo .venv/bin/python scripts/uninstall_systemd_units.py
```
### 10. Release gate for Stage 9

Stage 9 is accepted on hardware only when:

install works on Raspberry Pi
services survive reboot
acceptance script returns PASS
logs do not show recurring boot failures
runtime status confirms premium-ready startup