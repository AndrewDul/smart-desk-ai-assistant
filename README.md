# Smart Desk AI Assistant

A Raspberry Pi based smart desk assistant designed to support desk-based work through voice interaction, reminders, simple memory, focus sessions, break sessions, and OLED visual feedback.

This project is being developed as a practical embedded/IoT assistant prototype that combines hardware, software, and basic AI-driven interaction in one system.

---

## Project Overview

The main idea of this project is to build a smart stationary desk assistant that can help a user during work or study at a desk.

The assistant is intended to:
- accept simple voice commands
- speak back to the user
- store simple memory items
- create and trigger reminders
- manage focus and break sessions
- display useful information on a small OLED screen
- provide a more engaging assistant presence through simple animated visual behaviour

At the current stage, the project is focused on the **core stationary assistant without camera features**.

---

## Main Goals

The main goals of the current prototype are:

- build a working Raspberry Pi based assistant core
- implement voice input
- implement voice output
- implement a reminder system
- implement a simple memory system
- implement focus and break timing support
- display assistant states and feedback on OLED
- create a usable command flow for everyday desk interaction
- build a stable foundation for future expansion

---

## Additional / Future Goals

Planned future extensions may include:

- camera integration
- presence detection
- basic desk activity recognition
- richer assistant personality and expressions
- better speech recognition reliability
- improved microphone solution
- dashboard/log visualisation
- more advanced assistant states
- mobility as a possible optional extension

These are **not the priority right now**.  
The current priority is to complete a strong, working **stationary assistant core** first.

---

## Current Stage

**Stage 1: Core stationary assistant without camera**

At this stage, the project focuses on:
- Raspberry Pi setup
- hardware testing
- voice command support
- reminders
- memory
- timers
- OLED output
- assistant loop integration

---

## Current Features

The current prototype already includes:

- assistant boot and shutdown flow
- offline voice recognition using Vosk
- voice responses using `espeak-ng`
- simple command handling
- reminder creation and reminder triggering
- simple key-value memory
- recall of saved memory
- focus timer
- break timer
- timer stop support
- OLED text screens
- OLED idle eye animation
- OLED temporary menu/help/status screens
- background reminder checking
- log file support
- JSON-based persistent storage

---

## Hardware Used

Current hardware used in the project:

- Raspberry Pi 5
- 128 GB microSD card with Raspberry Pi OS
- active cooler for Raspberry Pi 5
- USB microphone
- speaker
- OLED display (I2C)
- keyboard
- mouse
- monitor

### Notes
- the current microphone works, but it captures too much background noise
- a better microphone or USB headset may be used later to improve voice recognition reliability

---

## Software and Technologies Used

### Current technologies
- Python 3
- Raspberry Pi OS
- Vosk (offline speech recognition)
- `espeak-ng` (voice output)
- `luma.oled` (OLED rendering)
- Pillow
- JSON for persistent project data

### Technologies likely to be used later
- OpenCV
- camera module tools
- computer vision based detection
- more advanced assistant logic
- optional dashboard / interface layer

---

## Project Structure

```text
SmartDeskAI_Assistant/
│
├── main.py
├── requirements.txt
├── README.md
│
├── config/
│   ├── settings.json
│   └── settings.example.json
│
├── data/
│   ├── memory.json
│   ├── reminders.json
│   ├── session_state.json
│   └── user_profile.json
│
├── docs/
│   ├── architecture_notes.md
│   ├── test_notes.md
│   └── troubleshooting.md
│
├── logs/
│   └── system.log
│
├── models/
│   └── vosk-model-small-en-us-0.15
│
├── modules/
│   ├── assistant_logic.py
│   ├── display.py
│   ├── memory.py
│   ├── reminders.py
│   ├── timer.py
│   ├── utils.py
│   ├── voice_in.py
│   └── voice_out.py
│
├── scripts/
└── tests/
```

## How the Assistant Works

### Basic flow

The assistant starts, enters a listening loop, and waits for a command.  
When the user speaks, the command is recognised offline and passed to the main assistant logic.  
The assistant then decides what action to take and responds through:

- voice output
- OLED display feedback
- state updates and log entries

### Main internal modules

- `main.py` - runs the main assistant loop
- `assistant_logic.py` - handles commands and connects the main parts of the system
- `voice_in.py` - listens for voice input and recognises commands
- `voice_out.py` - speaks assistant responses
- `display.py` - controls OLED text output and eye animation
- `memory.py` - stores and recalls simple key-value memory
- `reminders.py` - manages reminders
- `timer.py` - handles focus and break timing
- `utils.py` - shared helpers, paths, JSON handling, logging, and config loading

---

## How to Install and Run

### 1. Copy the project onto the Raspberry Pi

Place the project folder somewhere convenient on the Raspberry Pi, for example in a `Projects` folder.

### 2. Open Terminal in the project folder

Example:

```bash
cd ~/Projects/SmartDeskAI_Assistant
```
### 3. Create and activate a virtual environment
```
python3 -m venv .venv
source .venv/bin/activate
```
### 4. Install Python dependencies
```
pip install -r requirements.txt
```
### 5. Make sure required system packages are installed
```
sudo apt update
sudo apt install -y espeak-ng i2c-tools
```
### 6. Run the assistant
```
python main.py
```

---

## OLED Setup Note

The OLED display uses I2C communication.

Before using it, make sure that:

- I2C is enabled on the Raspberry Pi
- the OLED is wired correctly
- the configured I2C address matches the real device
- the current `display.py` version is the working one for the project

### Typical I2C OLED wiring

- `VCC`
- `GND`
- `SDA`
- `SCL`

### This makes it easier to change important runtime settings without editing the source code directly.

### At the moment, the config can be used for things like:

- microphone device index
- voice input timeout
- voice recognition debug mode
- OLED I2C address
- OLED size and rotation
- default overlay duration
- voice output engine

### A template version is also included here:

- config/settings.example.json

### Current Voice Commands
- Basic commands
- show help
- show status
- show memory
- show reminders
- show menu
- stop timer
- exit assistant

### Memory commands
- remember keys equals drawer
- recall keys

### Timer commands
- focus 1
- break 1

### Reminder commands
- remind me in 10 seconds to stretch

### Notes
- Short commands can be less reliable than clear full phrases.
- Microphone quality has a big effect on command recognition   accuracy.

### Example Usage

### Save memory
- remember keys equals drawer

### Recall memory
-recall keys

### Start focus mode
- focus 1

### Start break mode
- break 1

### Set a reminder
- remind me in 10 seconds to stretch

### Open the OLED menu screen
- show menu


### Known Limitations

### At the current stage, there are still a few known limitations:

- The current microphone is not ideal and picks up too much noise
- Voice recognition sometimes needs repeated commands
- The command set is still limited
- Camera features have not been added yet
- Mobility has not been added yet
- The dashboard is not implemented yet
- Some configuration support is still being integrated across the modules


### Development Notes

### Project progress is documented in:

- docs/architecture_notes.md
- docs/test_notes.md
- docs/troubleshooting.md

### These files are used to record:

- architecture decisions
- testing progress
- hardware and software issues
- fixes and improvements made during development


### Current Project Status

### The project already has a working Stage 1 assistant core prototype.

### At this point, it demonstrates:

- Raspberry Pi 5 embedded setup
- hardware and software integration
- offline voice interaction
- assistant state handling
- OLED feedback and eye animation
- reminders, memory, and timer logic

This gives the project a solid base for further development and for the final project demonstration.

### Author

Andrzej Dul
Software Engineering
De Montfort University

