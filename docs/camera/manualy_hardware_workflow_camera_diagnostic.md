


### Manualny hardware workflow, zgodnie z Twoją zasadą:

sudo systemctl stop nexa.service
cd ~/Projects/smart-desk-ai-assistant
python tests/vision/hardware/debug/camera_diagnostics_preview.py
sudo systemctl start nexa.service
Sterowanie w preview
q lub Esc — wyjście
s — zapis PNG + JSON diagnostics
p — pause / resume