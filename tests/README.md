# NeXa Test Suite

This directory contains all tests, benchmarks, hardware smoke tests, and validation scripts for the NeXa smart desk AI assistant.

Run with:

```bash
.venv/bin/python -m pytest -q
```

---

## Directory Structure

```
tests/
  conftest.py                  # Shared fixtures and pytest configuration
  support/                     # Shared test helpers and fakes

  core/                        # Core assistant logic
    calculator/                # Arithmetic parsing
    command_intents/           # Intent resolution and confidence policy
    vision/                    # Look-at-user dry-run bridge
    voice_engine/              # Voice pipeline settings and routing

  devices/                     # Device-level unit tests
    audio/                     # ASR, VAD, realtime audio bus, command grammar
    mobile_base/               # Mobile base controller and safety
    pan_tilt/                  # Pan-tilt servo protocol and calibration

  features/                    # Feature-level tests
    focus_vision/              # Focus tracking, presence detection, reminders
    test_*.py                  # Memory, reminders, guided flows, notifications

  integration/                 # Cross-module integration tests
    core/                      # Voice command flows, timer+focus interactions

  presentation/                # Visual Shell
    visual_shell/              # Feedback mode, snapshot builder, controller

  runtime/                     # Runtime pipeline tests
    diagnostics/               # Audio, OAK-D, wake word, time command probes
    drive_mode/                # Drive mode voice and keyboard
    health/                    # Espeak fallback policy
    main_loop/                 # Wake and barge-in safety defaults
    validation/                # Mobile base yaw assist
    voice_engine_v2/           # Full voice engine v2 test suite

  scripts/                     # Tests that validate scripts/ CLI tools
                               # (scripts stay in scripts/, these test them)

  unit/                        # Focused unit tests
    audio/                     # Wake gate, input device selector
    parsing/                   # Intent parser
    services/                  # Memory, reminders, timers, SQLite index

  vision/                      # Vision subsystem
    hardware/camera/           # Camera smoke tests (require hardware)
    hardware/debug/            # Camera diagnostics preview
    integration/               # Vision + runtime builder bridge
    unit/                      # Per-module unit tests
      behavior/                # Activity detection interpreters
      camera_service/          # Camera service broker and capture
      diagnostics/             # Calibration and overlay rendering
      fusion/                  # Snapshot builder
      look_at_me/              # Tracking planners and sessions
      perception/              # Face, person, object detection
      preprocessing/           # YOLO letterbox
      runtime/                 # AI broker lifecycle and hooks
      sessions/                # Tracker
      stabilization/           # Stabilization pipeline
      tracking/                # Motion executor, pan-tilt, target selector

  benchmarks/                  # Benchmark tests (use benchmarks/ library at repo root)
    voice/                     # Command latency, endpointing, full voice turn
    vision/                    # Look-at-me smoothness benchmark

  hardware/                    # Manual hardware smoke tests (not run by CI)
    display/lcd/               # LCD display tests including Waveshare vendor code
    pan_tilt/                  # Pan-tilt movement smoke tests
    ugv02/                     # UGV-02 mobile base movement tests

  docs/                        # Tests that validate documentation runbooks
```

---

## Test Categories

| Category                      | Description |              Run in CI |
|-------------------------------|-------------|------------------------|
| `core/`, `features/`, `unit/` | Unit tests — mocked hardware | Yes |
| `devices/`, `runtime/`, `vision/unit/` | Module tests — mostly mocked | Yes |
| `integration/` | Integration flows | Yes |
| `presentation/` | Visual Shell | Yes |
| `benchmarks/` | Performance benchmarks | Yes (dry-run) |
| `runtime/diagnostics/` | Probe scripts | Yes (dry-run) |
| `hardware/` | Physical hardware tests | Manual only |
| `vision/hardware/` | Camera hardware tests | Manual only |
| `scripts/` | Script coverage | Yes |

---

## Benchmark Library

The `benchmarks/` directory at the **repository root** contains the benchmark runner library (not tests). Tests in `tests/benchmarks/voice/` import from it:

```
benchmarks/              ← implementation library
  voice/
    benchmark_command_latency.py
    benchmark_endpointing_latency.py
    benchmark_full_voice_turn.py

tests/benchmarks/        ← pytest wrappers
  voice/
    test_benchmark_command_latency.py
    ...
  vision/
    test_look_at_me_smoothness_benchmark.py
```

---

## Known Limitations

- Hardware tests in `tests/hardware/` and `tests/vision/hardware/` require physical devices (pan-tilt, camera, LCD) and must be run manually.
- The Waveshare vendor code in `tests/hardware/display/lcd/vendor/` is third-party and not run by pytest.
- Some probe scripts in `tests/runtime/diagnostics/` require live hardware (OAK-D Lite, audio input).
