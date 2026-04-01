# Architecture Notes

## Project
Smart Desk AI Assistant

## Current stage
Stage 1 - stationary assistant core without camera

---

## 1. Project intention

The goal of this project is to build a Raspberry Pi based desk assistant that can support desk work through:
- voice interaction
- reminders
- simple memory
- focus timer
- break timer
- OLED visual feedback
- basic internal assistant logic

At this stage, the project is focused on the stationary assistant core only.
Camera features, computer vision, mobility, and other advanced hardware extensions are planned for later stages.

---

## 2. Hardware used so far

Current hardware used in the project:
- Raspberry Pi 5
- 128 GB microSD card with Raspberry Pi OS
- active cooler for Raspberry Pi 5
- USB microphone
- speaker
- OLED display
- keyboard
- mouse
- monitor

---

## 3. Early setup and hardware work completed

### Raspberry Pi 5 setup
The Raspberry Pi 5 was prepared as the main development platform for the assistant.

Completed setup tasks:
- Raspberry Pi OS installed on a 128 GB microSD card
- Raspberry Pi connected to Wi-Fi
- system updated
- keyboard and mouse connected and tested
- speaker connected and tested
- USB microphone connected
- active cooler installed and tested

### Cooling test
Cooling was tested manually by:
- monitoring temperature from terminal
- opening multiple browser tabs
- playing video content
- checking whether temperature increased under heavier use

Result:
- the active cooler worked correctly
- the Raspberry Pi stayed stable during testing
- temperature remained under control during normal manual stress testing

### Audio testing
Speaker testing:
- output audio was confirmed working

Microphone testing:
- microphone was detected and tested
- microphone worked, but quality was not ideal
- the current microphone captured too much noise
- this affected voice recognition reliability

### OLED testing
OLED testing started after I2C setup and troubleshooting.

Progress:
- simple OLED test screen was successfully displayed
- the display module was then extended to support:
  - animated eyes
  - blinking
  - left / centre / right gaze loop
  - timed text overlays such as menu or status screens

---

## 4. Current software architecture

The current architecture is modular.

### `main.py`
Main entry point of the assistant.

Responsibilities:
- create the assistant object
- boot the system
- keep the listening loop running
- pass recognized commands to the assistant logic
- shut down cleanly

### `modules/assistant_logic.py`
Core orchestration module.

Responsibilities:
- initialize all main modules
- handle commands
- update session state
- coordinate timers, reminders, memory, display, and voice output
- run the reminder background loop

### `modules/voice_in.py`
Voice input module.

Responsibilities:
- listen from microphone
- run offline speech recognition using Vosk
- map recognized phrases to supported assistant commands

### `modules/voice_out.py`
Voice output module.

Responsibilities:
- speak assistant responses using `espeak-ng`
- print assistant output to terminal
- append spoken output to logs

### `modules/display.py`
OLED display module.

Responsibilities:
- run a background OLED rendering loop
- show idle eye animation
- blink automatically
- look left / centre / right in a repeating loop
- temporarily switch to text screens such as:
  - boot screen
  - status
  - reminders
  - help
  - menu

### `modules/memory.py`
Simple key-value memory storage.

Responsibilities:
- save remembered facts
- recall saved facts
- return full memory list

### `modules/reminders.py`
Reminder manager.

Responsibilities:
- save reminders
- check due reminders
- mark reminder status
- list stored reminders

### `modules/timer.py`
Session timer module.

Responsibilities:
- start focus timer
- start break timer
- stop running timer
- report timer status
- call assistant callbacks on start / finish / stop

### `modules/utils.py`
Project support utilities.

Responsibilities:
- JSON load/save helpers
- log writing
- project file initialization
- data and log path definitions

---

## 5. Data flow

### Voice command flow
1. user speaks a command
2. `voice_in.py` listens through the microphone
3. Vosk recognizes speech
4. recognized speech is mapped to a supported command
5. `main.py` sends the command to `assistant_logic.py`
6. `assistant_logic.py` executes the correct action
7. result is shown on OLED and/or spoken back through `voice_out.py`

### Reminder flow
1. reminder is created
2. reminder is saved to JSON
3. reminder background thread checks reminders continuously
4. when due, the assistant:
   - shows reminder on OLED
   - speaks reminder aloud
   - writes event to log

### Memory flow
1. user says `remember key equals value`
2. memory item is stored in JSON
3. user can later request `recall key`
4. assistant reads the value back

---

## 6. Data storage

Current persistent files:
- `data/memory.json`
- `data/reminders.json`
- `data/session_state.json`
- `data/user_profile.json`
- `logs/system.log`

This makes the current prototype simple and easy to inspect, debug, and demonstrate.

---

## 7. Current limitations

Known limitations at this stage:
- current microphone captures too much background noise
- voice recognition still sometimes requires repeated commands
- device index for microphone is still hardcoded
- settings file exists but is not yet fully integrated into all modules
- no camera features yet
- no mobility features yet
- no dashboard yet
- command vocabulary is still limited

---

## 8. Current state of the prototype

The current prototype already supports:
- assistant boot and shutdown
- voice input
- voice output
- OLED output
- animated eyes on OLED
- menu screen on OLED
- help command
- status display
- simple memory
- reminders
- focus timer
- break timer
- stop timer
- background reminder loop
- logging

This means the project already has a real working stage 1 core prototype.

---

## 9. Next architectural improvements

Planned next improvements:
- move hardware and runtime parameters into config-driven loading
- improve microphone quality and command recognition reliability
- clean the repository structure
- improve test coverage
- prepare camera integration stage
- extend the assistant with richer states and better visual expressions