# NeXa

**NeXa** is my local bilingual desk companion built on **Raspberry Pi 5**.  
I am building it as a premium offline assistant for **desk work, studying, focus sessions, short breaks, and natural short conversation**.

The goal is not to create a rigid command box.  
I want NeXa to feel more like a **small local companion** that can talk, support, remember context, and use practical desk tools when needed.

NeXa is designed to:

- talk in **English and Polish**
- understand the difference between **conversation** and **commands**
- use tools such as reminders, timers, focus mode, and memory
- remember recent context from a conversation
- support work and studying at the desk
- stay **fast and responsive** on local hardware

At the current stage, NeXa is focused on a **stationary premium conversation core**.  
The main priority is to build a strong local desk companion first.  
Camera-based awareness and mobility come later.

---

## ✨ Project Overview

**NeXa** is a local embedded assistant designed for everyday desk life.

It is meant to help with:

- studying
- desk work
- short natural conversation
- reminders
- timers
- focus sessions
- short breaks
- quick memory
- assistant presence through voice and screen feedback

This project is also my **final project / embedded systems style build**, but I am treating it as something more than university prototype.  
The long-term goal is to turn it into a real premium local companion.

---

## 🎯 Main Goal

The main goal of NeXa is to build a **fast, local, bilingual, premium desk companion** on Raspberry Pi 5.

I want the system to:

- work offline
- feel more natural than a simple voice command bot
- support both **conversation** and **tool use**
- stay scalable without turning into hundreds of hardcoded `if` statements
- keep a clean architecture that can later grow into **camera-based awareness** and **mobility**

---

## What NeXa Can Do Right Now

At the current stage, NeXa already supports a strong part of the desk companion core.

### Voice Interaction

NeXa can currently:

- listen through a microphone
- detect speech with VAD
- transcribe speech offline
- speak back using local TTS
- work in **English and Polish**
- keep responses short and clear
- handle confirmation flows like **yes / no**
- deal better with many common short STT mistakes

### Conversation and Routing

NeXa already has a real routing layer.

It can separate requests into:

- **action** - direct command like timer, reminder, memory, help, status
- **conversation** - short companion-style replies
- **mixed** - a reply plus a related action
- **unclear** - when the request still needs clarification

This is important because NeXa is being built as a **desk companion**, not only as a command list.

### Time and Desk Utility Features

NeXa can currently handle:

- current time
- current date
- current day
- current year
- optional screen display offers for time/date/day/year
- help
- status
- introduction / assistant identity
- exit assistant
- shutdown system flow

### Memory

NeXa can currently:

- store short memory facts
- recall saved memory
- forget selected memory items
- list memory
- clear memory

### Reminders

NeXa can currently:

- create reminders
- list reminders
- delete a selected reminder
- clear all reminders
- trigger reminders in the background

### Timer / Focus / Break

NeXa can currently:

- start a normal timer
- start focus mode
- start break mode
- stop timer / focus / break
- keep session state
- show timer-related feedback on the screen
- speak timer-related updates

### Display Feedback

NeXa uses a real display layer, not just terminal output.

It can:

- show boot screens
- show help and status blocks
- show time/date/day/year blocks
- show reminder blocks
- show conversation summary blocks
- show confirmation screens
- display short feedback that matches the voice reply

### Logging and Persistence

NeXa stores local data and runtime state.

It keeps:

- memory entries
- reminders
- user profile
- session state
- runtime logs

---

## 🛠️ Current Hardware

This is the hardware used for the current NeXa build:

- **Raspberry Pi 5**
- **16 GB RAM**
- **128 GB microSD card**
- **active cooler**
- **ReSpeaker microphone setup**
- **Waveshare 2-inch LCD module**
- **speaker / audio output**
- **Raspberry Pi Camera Module 3** planned for the next stage
- keyboard / mouse / monitor during development

### Notes About the Hardware

- The current build is a **stationary desk companion**
- The Waveshare display is the current main assistant screen
- Cooling matters because NeXa runs local speech and assistant logic directly on the Pi
- The microphone quality has a huge effect on the full experience, so audio setup matters a lot

---

## 🧠 Current Software Stack

NeXa is Python-based and built in a modular way.

### Core Stack

- **Python 3**
- **Raspberry Pi OS**
- modular Python architecture
- JSON persistence
- **pytest** for tests

### Voice Input

Current main speech input path:

- **Faster-Whisper**
- **Silero VAD**
- **ONNX Runtime**
- `sounddevice`
- `soundfile`
- `numpy`

Current config is tuned for low latency:

- language: `auto`
- compute type: `int8`
- beam size: `1`
- best_of: `1`
- short silence and pre-roll tuning
- transcript filtering in the main loop

There is also legacy / optional support prepared for:

- **whisper.cpp**

### Voice Output

Current TTS path:

- **Piper**
- Polish voice:
  - `pl_PL-gosia-medium`
- English voice:
  - `en_GB-jenny_dioco-medium`

Fallback support:

- **espeak-ng**

### Display

Current display stack:

- custom display backend in `modules/io/display.py`
- **Waveshare 2-inch LCD**
- **SPI**
- `spidev`
- `rpi-lgpio`
- `gpiozero`
- `Pillow`

### Intent and Conversation Logic

Current logic stack:

- intent parser
- semantic companion router
- semantic intent matcher
- utterance normalizer
- conversation memory
- companion dialogue service
- response streaming layer

### Optional Local LLM Path

The project already contains a local LLM layer in code.

Prepared path:

- **llama.cpp**
- `llama-cli` support
- `llama-server` support
- configured model path for:
  - **Qwen2.5-1.5B-Instruct GGUF**

Important note:

- the local LLM path already exists in the code
- the current default runtime still has it **disabled**
- this means the system is already prepared for stronger local conversation, but that mode is not yet the default one

---

## Current Project Stage

Current stage:

- **version:** `0.6.1-low-latency-core`
- **stage:** `stage-1-stationary-premium-conversation`

What that means in practice:

- the system is already beyond a very simple prototype
- the desk companion core is modular and real
- low latency is a major priority
- the next big step is stronger short-form local conversation
- camera awareness and mobility come after the conversation core is stable

---

## How NeXa Works

This is the current system flow in simple terms.

### 1. Boot

`main.py` starts the assistant and runs startup checks.

NeXa:

- loads settings
- builds runtime services
- starts reminders and timer support
- prepares display and voice backends
- shows a boot screen
- enters the voice loop

### 2. Listening

The assistant listens for speech using the Faster-Whisper input layer.

That layer does things like:

- capture microphone audio
- use VAD to detect speech
- trim silence
- transcribe the audio
- try rescue passes for language handling
- reject some non-speech garbage

### 3. Text Cleanup and Normalization

Before the request reaches the router, NeXa cleans the text.

This layer:

- normalizes English and Polish phrases
- repairs common STT distortions
- helps routing stay stable
- improves cases like:
  - time questions
  - assistant identity
  - exit / shutdown phrases
  - short follow-ups

### 4. Language Handling

NeXa keeps track of language per turn.

This matters because it should:

- answer in the same language when possible
- keep Polish requests in Polish
- keep English requests in English
- avoid random language jumps after STT mistakes

### 5. Routing

The router decides whether the input is:

- an action
- a conversation turn
- a mixed turn
- an unclear turn

This is one of the most important parts of the project, because it allows NeXa to grow without becoming a giant mess of manual exceptions.

### 6. Action Execution

If the request is a direct action, it goes through the core dispatch layer.

That layer calls the right handler for things like:

- time/date/day/year
- help/status
- memory
- reminders
- timer/focus/break
- exit/shutdown

### 7. Dialogue Reply

If the request is more conversational, it goes through the dialogue service.

Right now this uses:

- deterministic replies
- template-based short conversation
- small knowledge-style replies
- recent conversation context
- optional local LLM support prepared in code

### 8. Response Streaming

Replies go through a streaming response layer.

That layer helps with:

- chunking replies
- quick ACK-style starts
- smoother voice timing
- better perceived speed
- better display summary generation

### 9. Voice + Display Output

Finally NeXa:

- speaks the answer
- shows a short matching display block
- stores relevant context if needed
- logs the turn

---

## Current Architecture

The project is already split into clear layers.

### Runtime Layer

Main file:

- `modules/runtime_builder.py`

This layer is responsible for:

- loading settings
- creating parser/router/dialogue
- building voice input backend
- building voice output backend
- building display backend
- loading memory / reminders / timer services
- graceful fallback when something is missing

### Core Assistant Layer

Main file:

- `modules/core/assistant.py`

This is the central controller.  
It handles:

- session state
- pending follow-ups
- confirmations
- language decisions
- semantic overrides
- conversation memory writes
- route handling
- action execution
- dialogue execution

### Core Action Handlers

Files in:

- `modules/core/`

These handle the direct assistant features.

Examples:

- `handlers_time.py`
- `handlers_system.py`
- `handlers_memory.py`
- `handlers_reminders.py`
- `handlers_timer.py`
- `handlers_focus.py`
- `handlers_break.py`
- `followups.py`
- `dispatch.py`

### I/O Layer

Files in:

- `modules/io/`

This is the hardware / input / output layer.

Examples:

- `faster_whisper_input.py`
- `whisper_input.py`
- `voice_out.py`
- `display.py`
- `text_input.py`

### NLU Layer

Files in:

- `modules/nlu/`

This is the understanding and routing support layer.

Examples:

- `router.py`
- `semantic_companion_router.py`
- `semantic_intent_matcher.py`
- `semantic_router.py`
- `utterance_normalizer.py`

### Parsing Layer

Files in:

- `modules/parsing/`

Main file:

- `intent_parser.py`

This is the structured command parser.

### Services Layer

Files in:

- `modules/services/`

This holds the assistant services.

Examples:

- `companion_dialogue.py`
- `conversation_memory.py`
- `local_llm.py`
- `memory.py`
- `reminders.py`
- `response_streamer.py`
- `timer.py`

### System Layer

Files in:

- `modules/system/`

This handles shared lower-level support.

Examples:

- `system_health.py`
- `utils.py`

---

## 📁 Project Structure

```text
SmartDeskAI_Assistant/
│
├── main.py
├── README.md
├── requirements.txt
├── pytest.ini
│
├── assets/
│   ├── audio/
│   └── icons/
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
├── modules/
│   ├── runtime_builder.py
│   ├── runtime_contracts.py
│   │
│   ├── core/
│   │   ├── assistant.py
│   │   ├── dispatch.py
│   │   ├── followups.py
│   │   ├── handlers_break.py
│   │   ├── handlers_focus.py
│   │   ├── handlers_memory.py
│   │   ├── handlers_reminders.py
│   │   ├── handlers_system.py
│   │   ├── handlers_time.py
│   │   ├── handlers_timer.py
│   │   ├── handlers_timers.py
│   │   ├── language.py
│   │   └── responses.py
│   │
│   ├── io/
│   │   ├── display.py
│   │   ├── faster_whisper_input.py
│   │   ├── text_input.py
│   │   ├── voice_out.py
│   │   └── whisper_input.py
│   │
│   ├── nlu/
│   │   ├── router.py
│   │   ├── semantic_companion_router.py
│   │   ├── semantic_intent_matcher.py
│   │   ├── semantic_router.py
│   │   └── utterance_normalizer.py
│   │
│   ├── parsing/
│   │   └── intent_parser.py
│   │
│   ├── services/
│   │   ├── companion_dialogue.py
│   │   ├── conversation_memory.py
│   │   ├── local_llm.py
│   │   ├── memory.py
│   │   ├── reminders.py
│   │   ├── response_streamer.py
│   │   └── timer.py
│   │
│   └── system/
│       ├── system_health.py
│       └── utils.py
│
└── tests/
    ├── conftest.py
    ├── integration/
    │   └── core/
    │       ├── test_timer_focus_break_flow.py
    │       └── test_voice_commands.py
    └── unit/
        ├── parsing/
        │   └── test_intent_parser.py
        └── services/
            ├── test_memory.py
            ├── test_reminders.py
            └── test_timer.py
```

---

## What the Main Files Are Responsible For

### Top Level

- `main.py`  
  Starts NeXa, runs the voice loop, filters low-value noise, and keeps the assistant alive during normal use.

- `requirements.txt`  
  Python packages used by the project.

- `pytest.ini`  
  pytest configuration.

### Config

- `config/settings.json`  
  Main runtime settings for the actual build.

- `config/settings.example.json`  
  Template config.

### Data

- `data/memory.json`  
  Stored memory entries.

- `data/reminders.json`  
  Stored reminders.

- `data/session_state.json`  
  Current assistant state, including active modes and timers.

- `data/user_profile.json`  
  User-facing assistant context, such as the user name and profile-level data.

### Docs

- `docs/architecture_notes.md`  
  Notes about architecture and design direction.

- `docs/test_notes.md`  
  Testing notes and progress notes.

- `docs/troubleshooting.md`  
  Known issues, fixes, and debugging notes.

### Logs

- `logs/system.log`  
  Runtime log file.

### Runtime and Contracts

- `modules/runtime_builder.py`  
  Builds the whole runtime and backends.

- `modules/runtime_contracts.py`  
  Shared response / chunk / plan contracts.

### Core

- `modules/core/assistant.py`  
  Main assistant controller that coordinates the whole runtime.

- `modules/core/dispatch.py`  
  Sends parsed actions to the correct handler.

- `modules/core/followups.py`  
  Handles yes/no flows and action follow-ups.

- `modules/core/handlers_time.py`  
  Time/date/day/year logic.

- `modules/core/handlers_system.py`  
  Help, status, self-introduction, exit, shutdown.

- `modules/core/handlers_memory.py`  
  Memory store / recall / forget / clear logic.

- `modules/core/handlers_reminders.py`  
  Reminder creation and reminder management.

- `modules/core/handlers_timer.py`  
  Timer start / stop logic.

- `modules/core/handlers_focus.py`  
  Focus mode logic.

- `modules/core/handlers_break.py`  
  Break mode logic.

- `modules/core/language.py`  
  Language helpers for Polish / English logic.

- `modules/core/responses.py`  
  Reusable response formatting and display helpers.

### I/O

- `modules/io/faster_whisper_input.py`  
  Main offline speech input backend.

- `modules/io/whisper_input.py`  
  Optional whisper.cpp-based backend.

- `modules/io/voice_out.py`  
  Speech output, Piper playback, fallback logic, and phrasing shaping.

- `modules/io/display.py`  
  Screen output for the Waveshare display.

- `modules/io/text_input.py`  
  Safe text input fallback for development or degraded mode.

### NLU

- `modules/nlu/router.py`  
  Route and intent structures.

- `modules/nlu/semantic_companion_router.py`  
  Main route logic for action / mixed / conversation / unclear.

- `modules/nlu/semantic_intent_matcher.py`  
  Optional semantic intent matching support.

- `modules/nlu/semantic_router.py`  
  Semantic support utilities.

- `modules/nlu/utterance_normalizer.py`  
  Normalization and repair of STT text before routing.

### Services

- `modules/services/companion_dialogue.py`  
  Conversation reply building and conversation behavior.

- `modules/services/conversation_memory.py`  
  Short recent-turn memory for conversation context.

- `modules/services/local_llm.py`  
  Local LLM integration layer for future / optional real conversation mode.

- `modules/services/memory.py`  
  Memory storage service.

- `modules/services/reminders.py`  
  Reminder storage and due-check logic.

- `modules/services/response_streamer.py`  
  Response plan execution and chunk timing.

- `modules/services/timer.py`  
  Timer engine.

### System

- `modules/system/system_health.py`  
  Runtime health / backend checks.

- `modules/system/utils.py`  
  common paths, logging, JSON helpers, config loading, and utility helpers.

---

## Current Models and What They Are Used For

### Speech-to-Text

Current default config:

- **Faster-Whisper**
- model size / path: `tiny`
- compute type: `int8`

Purpose:

- fast offline speech recognition
- short desk commands
- short conversation turns
- bilingual use with automatic language handling

### VAD

Current config uses:

- **Silero VAD**
- model path:
  - `models/ggml-silero-v6.2.0.bin`

Purpose:

- detect real speech
- trim silence
- reduce useless audio processing
- improve speed and responsiveness

### Text-to-Speech

Current Piper voices:

- Polish:
  - `pl_PL-gosia-medium`
- English:
  - `en_GB-jenny_dioco-medium`

Purpose:

- offline speech output
- bilingual assistant voice
- short and fast responses

### Prepared Local LLM Model

Prepared in config:

- **Qwen2.5-1.5B-Instruct-Q4_K_M.gguf**

Purpose:

- short local conversation
- short knowledge replies
- recent context use
- future natural assistant mode

Important:

- this model path already exists in config
- the local LLM service already exists in code
- the feature is still disabled in the current default runtime

---

## Example Commands

### Help and System

- `How can you help me`
- `Pomoc`
- `Status`
- `Kim jesteś`
- `Jak się nazywasz`
- `wyłącz asystenta`
- `wyłącz system`

### Time and Date

- `Która jest godzina`
- `Jaka jest data`
- `Jaki dzisiaj dzień`
- `Jaki jest rok`
- `Pokaż godzinę`

### Memory

- `zapamiętaj że klucze są w kuchni`
- `co pamiętasz o kluczach`
- `zapomnij klucze`
- `pokaż pamięć`

### Reminders

- `przypomnij mi za 10 minut żeby zrobić przerwę`
- `pokaż przypomnienia`
- `usuń przypomnienie`

### Timer / Focus / Break

- `ustaw timer na 10 minut`
- `włącz focus na 25 minut`
- `włącz przerwę na 5 minut`
- `zatrzymaj timer`

### Short Conversation

The current conversation layer is still limited, but it already supports short companion-style turns better than a pure command bot.

Examples:

- `powiedz coś śmiesznego`
- `daj mi zagadkę`
- `powiedz ciekawostkę`
- `wytłumacz mi to`
- `no nie wiem`
- `jestem zmęczony`

---

## 🚀 How to Run the Project

### 1. Go to the project folder

```bash
cd ~/Projects/SmartDeskAI_Assistant
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

### 3. Activate it

```bash
source .venv/bin/activate
```

### 4. Install Python packages

```bash
pip install -r requirements.txt
```

### 5. Make sure basic system packages are available

For a normal Raspberry Pi setup, I usually want these installed:

```bash
sudo apt update
sudo apt install -y python3-venv alsa-utils ffmpeg espeak-ng
```

If display / GPIO support is needed, I also make sure the Pi is configured correctly for SPI.

### 6. Run NeXa

```bash
python main.py
```

---

## Display Setup Notes

Current display config is for:

- **Waveshare 2-inch LCD**
- **SPI**
- width: `240`
- height: `320`

Important notes:

- this is not the old OLED setup anymore
- the current display handling is aimed at the Waveshare screen
- display settings live in `config/settings.json`

Current relevant display settings include:

- driver
- interface
- width / height
- rotation
- SPI port / device
- GPIO pins for DC / RST / backlight
- overlay timing

---

## Audio Setup Notes

Current speech input settings matter a lot for performance.

Important current settings include:

- `engine: faster_whisper`
- `language: auto`
- `sample_rate: 16000`
- `max_record_seconds: 6.0`
- `end_silence_seconds: 0.55`
- `pre_roll_seconds: 0.45`
- `beam_size: 1`
- `best_of: 1`
- `compute_type: int8`

Why this matters:

- NeXa is tuned for low latency
- short command / short turn use matters more than long dictation
- speed matters much more than perfect long-form transcription

---

## Testing

Current tests in the repo include:

### Integration Tests

- `tests/integration/core/test_timer_focus_break_flow.py`
- `tests/integration/core/test_voice_commands.py`

### Unit Tests

- `tests/unit/parsing/test_intent_parser.py`
- `tests/unit/services/test_memory.py`
- `tests/unit/services/test_reminders.py`
- `tests/unit/services/test_timer.py`

Run all tests with:

```bash
pytest
```

---

## Current Limitations

This is the honest current state.

### What Is Already Good

- modular structure
- strong core for desk actions
- better routing than a simple command-only assistant
- solid base for memory / reminders / timer flow
- bilingual structure
- real screen + voice integration
- prepared local LLM path already exists
- strong direction for premium local companion behavior

### What Is Still Limited

- full local conversation is not the default mode yet
- local LLM path is still disabled by default
- current TTS is improved, but still not a fully premium natural voice
- speech recognition can still distort short Polish phrases
- knowledge answers are still limited in the current default mode
- long free conversation is not ready yet
- camera features are not added yet
- mobility is not added yet

---

## Development Direction

The next big goal is to move from:

- a strong modular desk assistant core

to:

- a short natural local bilingual desk companion

That means the next major area is:

- better real conversation
- short context memory in dialogue
- clearer difference between commands and conversation
- better local knowledge replies
- better natural voice feeling
- still keeping low latency on Raspberry Pi 5

---

## Planned Next Stage: Stronger Local Conversation

This is the next important stage for NeXa.

The goal is:

- I can say one or two short sentences to NeXa
- NeXa can answer with one or two short sentences
- it should still feel fast
- commands should still stay deterministic
- conversation should go through the local dialogue layer
- recent context should matter

Planned direction:

- enable local LLM runtime
- use the existing local LLM adapter
- keep tool use controlled by the current command system
- let the LLM handle short conversation and short knowledge replies
- keep answers intentionally short so the experience stays fast on Pi 5

---

## Planned Camera Stage

The next hardware expansion after the conversation core is the camera stage.

Planned hardware:

- **Raspberry Pi Camera Module 3**

Planned use:

- detect if somebody is sitting at the desk
- detect if the user is studying / working
- detect if the user is using a phone for too long during focus mode
- use that as context for assistant support

Example planned behavior:

- if focus mode is active
- and the camera sees that the user is spending too long on the phone
- NeXa will gently remind the user to get back to work or study

This is meant to support:

- focus
- study discipline
- better desk awareness
- smarter assistant context

Important note:

- camera features are planned
- they are not part of the current stable core yet

---

## Planned Long-Term Mobility Stage

Mobility is not the current priority, but it is already part of the long-term vision.

Planned direction:

- move NeXa from a stationary desk companion
- to a mobile assistant platform

Planned hardware direction:

- **Mecanum wheels platform**

Why Mecanum wheels:

- compact movement
- sideways movement
- flexible movement around a room or desk area
- a better premium robotics direction than a simple basic wheeled base

Important note:

- mobility is a bonus end-stage extension
- the current priority remains:
  - stable conversation
  - stable assistant core
  - camera-based desk awareness
  - then mobility

---

## Long-Term Vision

My long-term vision for NeXa is:

- premium local desk companion
- bilingual Polish / English interaction
- short natural conversation
- useful tool use
- memory of recent context
- study and desk-work support
- smart focus / break support
- camera-based desk awareness
- optional mobility in the final extended version

I want NeXa to feel like a real companion at the desk, not just a speaker that reacts to isolated commands.

---

## Current Status in One Sentence

NeXa is already a real modular Raspberry Pi desk assistant core, and the next major step is turning it into a fast short-form local bilingual companion with better conversation, better context, camera awareness, and later optional mobility.

---

## Author

**Andrzej Dul**  
Software Engineering  
De Montfort University