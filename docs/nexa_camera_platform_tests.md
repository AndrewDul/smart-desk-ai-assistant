# NeXa — Camera Platform Movement Tests

## 1. Stop NeXa service

Use this first so nothing else is using GPIO / I2C.

```bash
sudo systemctl stop nexa.service
```

## 2. Go to project and activate virtual environment

```bash
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
```

## 3. Check I2C device visibility

If address `40` appears, the pan-tilt controller is visible.

```bash
sudo i2cdetect -y 1
```

## 4. Basic pan-tilt movement smoke test

This is the main first hardware test.

```bash
python tests/hardware/pan_tilt/pan_tilt_manual_smoke.py
```

What it does:
- center
- left / right / up / down
- diagonal
- circle
- speed demo
- wave
- return to center

## 5. Advanced movement behaviour test

This checks more expressive movement patterns.

```bash
python tests/hardware/pan_tilt/pan_tilt_behavior.py
```

What it does:
- speed profiles
- ultra smooth movement
- laugh
- disagree
- anger
- happiness
- curiosity
- surprise
- sadness
- confidence

## 6. Movement + LCD face test

Run this if you want pan-tilt movement together with the LCD face.

```bash
python tests/hardware/pan_tilt/pan_tilt_behavior_face.py
```

## 7. If normal Python run fails because of permissions

Use the virtualenv Python with sudo:

```bash
sudo -E .venv/bin/python tests/hardware/pan_tilt/pan_tilt_manual_smoke.py
```

or:

```bash
sudo -E .venv/bin/python tests/hardware/pan_tilt/pan_tilt_behavior.py
```

## 8. Start NeXa again after tests

```bash
sudo systemctl start nexa.service
```

## 9. Recommended full sequence

```bash
sudo systemctl stop nexa.service
cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate
sudo i2cdetect -y 1
python tests/hardware/pan_tilt/pan_tilt_manual_smoke.py
python tests/hardware/pan_tilt/pan_tilt_behavior.py
python tests/hardware/pan_tilt/pan_tilt_behavior_face.py
sudo systemctl start nexa.service
```
