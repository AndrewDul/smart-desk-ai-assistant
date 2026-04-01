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

## Voice Interaction Architecture Update

### Overview

The voice interaction layer was upgraded from a Vosk-first command approach to a Whisper-based bilingual speech pipeline designed for more natural spoken input in both Polish and English.

The current goal of this layer is to support:
- offline speech recognition on Raspberry Pi
- bilingual command understanding
- natural phrase-based commands instead of rigid syntax
- localized responses based on the detected language of the user
- context-aware follow-up behaviour such as asking for clarification or asking for the user's name

### Main Components

#### 1. Whisper Speech Recognition Layer
The assistant now uses `whisper.cpp` as the main speech recognition engine instead of relying only on the earlier Vosk command model.

This change was introduced because Whisper provided noticeably better recognition quality for:
- Polish speech
- English speech
- mixed natural phrasing
- less rigid command wording

The implementation uses a custom `WhisperVoiceInput` module that:
- records audio from the selected microphone
- detects a supported sample rate dynamically
- saves the utterance to a temporary WAV file
- sends the file to `whisper-cli`
- returns the final transcript to the assistant

#### 2. Device-Aware Audio Input
The input layer was improved so the microphone can be selected by device name instead of relying only on a fixed device index.

This makes the project more stable because audio device indices may change after reboot, reconnecting USB devices, or changing audio configuration.

A fallback mechanism was also added to choose a supported input sample rate automatically, because the USB microphone used in testing did not accept 16000 Hz directly.

#### 3. Intent Parsing Layer
A dedicated `IntentParser` was added to convert raw transcripts into structured assistant actions.

Instead of requiring strict formats such as:
- `remember key = value`
- `remind 10 | message`

the assistant can now interpret more natural examples such as:
- `klucze sa w kuchni`
- `gdzie sa klucze`
- `przypomnij mi za 10 sekund zebym wstal`
- `introduce yourself`
- `która godzina`

The parser currently supports:
- help and menu commands
- status requests
- memory storage
- memory recall
- reminder creation
- focus and break timer commands
- introduction queries
- time queries
- fuzzy matching for unclear commands

#### 4. Assistant Logic Layer
The `CoreAssistant` class was updated so that the assistant no longer only reacts to fixed English commands.

The new logic now:
- detects whether the user is speaking Polish or English
- answers in the same language
- shows localized menu/help output
- introduces itself when asked
- asks the user for their name after introducing itself
- stores the conversation partner name in the user profile
- answers time questions in the same language as the question
- asks for clarification when the spoken command is unclear

#### 5. Clarification and Confirmation Flow
If the transcript is close to a known command but not fully correct, the assistant does not immediately fail.

Instead, it can enter a clarification state and ask what the user meant, for example by suggesting a likely command such as status or menu.

This is important because speech recognition may still produce near-matches rather than exact command phrases.

#### 6. Text-to-Speech Layer
The current speech output still uses `espeak-ng` because it is lightweight and easy to run locally on Raspberry Pi.

The output layer was improved to:
- support Polish and English voice selection
- support language-dependent speaking
- support a female voice variant

However, this is still considered a temporary solution because the voice remains too robotic for the intended final experience.

A future improvement is planned to replace or augment the current TTS layer with a more natural local voice engine.

### Current Voice Interaction Flow

1. User speaks into USB microphone  
2. Audio is captured using the selected input device  
3. A supported sample rate is chosen automatically  
4. Audio is written to a temporary WAV file  
5. `whisper.cpp` transcribes the utterance  
6. The transcript is passed to `IntentParser`  
7. The parser returns a structured intent  
8. `CoreAssistant` decides:
   - what to display
   - what to say
   - whether to save memory
   - whether to ask a follow-up question
   - whether to request clarification
9. A localized text response is spoken back to the user

### Design Rationale

This architecture was chosen because it improves the realism and usability of the prototype without requiring cloud services.

Compared with the earlier command-only voice input approach, this design:
- improves speech recognition quality
- makes commands more natural
- supports both Polish and English
- creates a more convincing desk assistant interaction model
- better matches the project aim of an intelligent assistant rather than a fixed voice menu

### Current Limitations

The current architecture still has some limitations:
- very short utterances may still be mis-transcribed occasionally
- language auto-detection may not always be reliable for extremely short inputs
- the current TTS voice is still too synthetic
- clarification logic is still simple and can be expanded
- dialogue memory is still shallow and task-oriented rather than conversational

### Planned Next Improvements

Planned next steps for this voice architecture include:
- replacing the current TTS with a more natural local voice
- improving clarification flow for ambiguous commands
- expanding bilingual command coverage
- improving name capture and user dialogue flow
- adding more conversational intents
- optionally adding grammar-guided decoding for high-priority commands