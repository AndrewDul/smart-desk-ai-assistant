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

## Conversational Interaction Layer

The assistant architecture was extended from a simple command-driven prototype into a more natural conversational interaction layer. The main goal of this update was to improve usability, support bilingual interaction, and make the system feel more like a real desk assistant rather than a strict command parser.

### Main interaction flow

The startup flow was redesigned so that the OLED first shows a short **DevDul** branding screen, then returns to the default animated eyes state, and only after that the assistant speaks its greeting in English. This creates a cleaner and more deliberate boot experience.

The default OLED state is now the animated eyes display. Informational screens such as reminders, time, memory recall results, and help summaries are shown only as temporary overlays. After the overlay timeout, the display automatically returns to the eyes animation.

### Conversational architecture

The assistant now uses a layered interaction model:

1. **Speech Input Layer**  
   Audio is captured locally and transcribed using Whisper-based offline speech recognition. Blank audio, silence markers, and low-value filler noise are filtered before command handling.

2. **Intent Parsing Layer**  
   The intent parser maps natural Polish and English phrases to internal actions. This includes:
   - help queries
   - self-introduction
   - time/date/day/year requests
   - reminder creation
   - memory storage and recall
   - timer, focus mode, and break mode
   - stop/cancel variants
   - fuzzy matching with confirmation prompts

3. **Conversation State Layer**  
   The assistant keeps temporary interaction state for multi-step flows. This includes:
   - waiting for a name
   - waiting for permission to remember the name
   - waiting for timer/focus/break duration
   - waiting for yes/no confirmation
   - waiting for whether information should also be shown on the OLED

4. **Action Execution Layer**  
   Once an intent is resolved, the assistant executes the requested behaviour through its core modules:
   - memory
   - reminders
   - session timer
   - OLED display
   - speech output

### Bilingual behaviour

The assistant now adapts its spoken responses to the language used by the user. If the user speaks Polish, the assistant responds in Polish. If the user speaks English, it responds in English. The system still starts with an English greeting, but subsequent interaction follows the detected user language.

### Memory and recall design

The memory component was extended to support more natural storage and retrieval. The user can store information using phrases such as:

- “Remember that my keys are in the kitchen”
- “Zapamiętaj że klucze są w kuchni”

The recall layer supports natural follow-up questions such as:

- “Where are my keys?”
- “Gdzie są moje klucze?”

Matching is more tolerant than exact string matching, which improves usability in real spoken interaction.

### Focus and break flow

The focus mode was redesigned as a conversational workflow. If the user says “focus mode”, the assistant asks how long the session should be. After the focus session ends, the assistant asks whether the user wants a break and can then ask for break duration. This creates a more natural study-support workflow even before camera-based focus monitoring is added.

### Testing support

To improve stability, automated tests were added for:
- intent parsing
- memory behaviour
- reminders
- session timer logic
- higher-level conversational command scenarios



## Refactor of the project structure

To make the project easier to maintain and safer to extend, I reorganised the codebase into a clearer modular structure. The goal of this refactor was to separate responsibilities, reduce architectural confusion, and prepare the project for future development without relying on flat module placement.

The project was previously structured in a more mixed way, where multiple responsibilities existed close together in the same level of the `modules` directory. As the Smart Desk AI Assistant started to grow, this became harder to manage. Logic related to assistant behaviour, device input/output, timers, reminders, parsing, and shared utilities needed a clearer separation.

The refactor introduced a layered module structure inside the `modules` directory:

- `modules/core/`  
  contains the main assistant orchestration logic and central runtime behaviour

- `modules/io/`  
  contains input and output related components such as display handling, text input, voice input, and voice output

- `modules/services/`  
  contains internal application services such as reminders, memory, and timer management

- `modules/parsing/`  
  contains intent parsing and command interpretation logic

- `modules/system/`  
  contains shared system-level utilities such as settings loading, file handling, logging, and health checking

This refactor was designed to improve separation of concerns.

The `core` layer now acts as the central coordinator of the assistant.  
The `io` layer is responsible for interaction with the outside world.  
The `services` layer holds reusable internal logic that supports assistant features.  
The `parsing` layer is responsible for interpreting user commands.  
The `system` layer provides project-wide support functions and runtime checks.

This change improves the architecture in several ways.

First, it makes the project easier to understand because each file now belongs to a clearer functional area.  
Second, it reduces the risk of future changes affecting unrelated parts of the system.  
Third, it supports safer long-term maintenance by giving the project a more scalable internal layout.  
Finally, it creates a stronger foundation for future cleanup, including the removal of temporary legacy compatibility files that were kept only during the transition period.

From an architectural point of view, this refactor moves the project from a flatter and more tightly mixed structure toward a more organised modular design. This is important for a system such as Smart Desk AI Assistant, where hardware interaction, assistant logic, timers, memory, reminders, speech handling, and configuration management all need to work together without becoming tangled.

This refactor does not change the main purpose of the system. Instead, it improves the internal structure so that future development can continue more cleanly and with lower risk.


## Test Structure Reorganisation and Logic Stabilisation

I reorganised the automated test suite into a clearer structure based on test purpose.  
The tests are now separated into unit and integration areas, with a shared configuration under the main `tests` directory. This makes the test suite easier to understand, maintain, and extend as the project grows.

At the same time, I fixed several logic issues discovered through the updated test runs.  
The intent parser was improved so reminder deletion commands are interpreted more reliably, especially when the user refers to a reminder by message rather than by identifier. The reminder manager was also improved by cleaning reminder messages more consistently, supporting cleanup of completed reminders, and handling partially valid stored reminder entries more safely.

These changes improved both the internal organisation of the project and the reliability of the reminder-related assistant features. They also helped confirm that the refactored architecture remains stable under automated testing.

# Hardware and Display Architecture Update

## Overview

I updated the hardware setup of my Smart Desk AI Assistant during development.

At first, I was using a small OLED display and an older microphone setup. Later, I replaced them with a larger SPI LCD display and a much better USB microphone array to improve visual output and voice input quality.

This change improved the project a lot, especially for display size, readability, and microphone quality.

---

## New Hardware

### New LCD Display
I replaced the old OLED display with:

**Waveshare 2inch LCD Module**
- display controller: **ST7789V / ST7789VW**
- resolution: **240 x 320**
- interface: **SPI**
- colour display
- larger and clearer than the old OLED

This new display gives me much more screen space, so I can show text, status screens, and eye graphics more clearly than before.

### New Microphone
I replaced the old microphone with:

**Seeed Studio ReSpeaker XVF3800 USB 4-Mic Array**
- USB microphone array
- much cleaner input
- very low noise
- better voice pickup than the previous microphone

This microphone works very well for my assistant. The sound quality is much better than before and the captured voice is cleaner.

---

## Hardware Connections

### LCD connection to Raspberry Pi 5

The Waveshare 2inch LCD is connected through SPI.

| LCD Pin | Raspberry Pi Pin | GPIO / Function |
|---|---:|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| DIN | Pin 19 | GPIO10 / MOSI |
| CLK | Pin 23 | GPIO11 / SCLK |
| CS | Pin 24 | GPIO8 / CE0 |
| DC | Pin 22 | GPIO25 |
| RST | Pin 13 | GPIO27 |
| BL | Pin 12 | GPIO18 |

### Microphone connection

The ReSpeaker XVF3800 is connected directly by USB.

I use it only as a microphone.
I keep my separate USB speaker as the audio output device.

---

## Software Architecture Change

### Old display approach
At first, my project used the OLED display path and code based on a smaller monochrome screen.

This was suitable for early testing, but it was limited:
- very small screen area
- limited text output
- not suitable for more detailed status screens
- not suitable for a better face / eye visual style

### New display approach
After changing the hardware, I moved the display path toward the Waveshare LCD setup.

I tested multiple approaches:
- old OLED-style flow
- `luma.lcd`
- `st7789`
- direct Waveshare vendor driver

The direct Waveshare vendor driver was the only path that proved that the hardware itself was working correctly.

Because of that, the display architecture changed from a simple OLED path to a dedicated LCD path for the Waveshare 2inch module.

---

## Voice Input Architecture Change

### Old microphone setup
The earlier microphone worked, but the quality was worse and the signal was not as clean.

### New microphone setup
I now use the ReSpeaker XVF3800 as the main input device.

The microphone is detected by the system as a USB capture device and I configured my project to use it for voice input.

Important settings used:
- input device index: **2**
- sample rate: **16000 Hz**

This microphone is now the main voice input device in the system.

---

## Current Practical Architecture

### Input
- ReSpeaker XVF3800 USB 4-Mic Array for voice capture
- camera support planned / integrated separately
- keyboard or terminal still used for some debugging

### Output
- separate USB speaker for audio output
- Waveshare 2inch LCD for visual output

### Core system
- Raspberry Pi 5
- Python-based assistant logic
- reminder and memory systems
- voice input and output
- display output
- hardware test scripts and manual test scripts

---

## Display Rendering Direction

During testing I found that this LCD is more sensitive than the old OLED and it does not behave well with every Python display library.

Because of that, the display path now depends on the specific Waveshare 2inch LCD behaviour instead of treating it like a generic screen.

This is an important design note:
the display is not just "a screen", but a hardware-specific component that needs its own tested rendering path.

---

## Why this hardware change was a good decision

Changing the hardware was a good improvement for the project.

### LCD improvement
The new LCD is:
- larger
- easier to read
- much better for status screens
- much better for face / eye visuals than the old OLED

### Microphone improvement
The new microphone is:
- clearer
- cleaner
- more professional
- much better for speech recognition than the old microphone

Overall, this hardware change made the assistant feel more like a real system and less like an early prototype.


## Voice assistant architecture update - bilingual support and speech pipeline improvements

During this stage I focused mainly on improving the voice assistant core and making the system easier to grow later.

At the beginning, the logic for timers and assistant flow was getting too mixed in bigger files. Because of that, I separated the timer-related features into smaller modules. I created separate handlers for:

- normal timer
- focus mode
- break mode

This made the project structure much cleaner. The main assistant file is now more focused on coordination, while the real behaviour for timer, focus, and break is handled in dedicated files. This is better for future development because these features will probably grow a lot later.

I also improved the main command flow of the assistant. The startup was updated so the assistant starts in English as the main language, introduces itself, and tells the user that it can also work in Polish. The help flow was also improved, so the assistant can explain its current main features in a more clear way.

Another important change was the follow-up and confirmation system. I improved the behaviour for things like:

- yes / no
- tak / nie
- choosing between possible meanings
- timer duration follow-up
- focus and break follow-up
- exit and shutdown confirmation

This made the assistant feel more structured and more like a real product instead of a collection of disconnected commands.

The biggest technical work in this stage was the speech recognition pipeline. I spent a lot of time trying to improve Polish and English command recognition. At first I tried to solve it mostly through parser logic and language rules, but that did not give good enough real-life results. The assistant was still misunderstanding short Polish commands and sometimes mixing languages in replies.

Because of that, I changed the Whisper model from base to small. This gave a clear improvement immediately. After this change, the assistant started understanding Polish and English much better and it could recognise the main commands much more reliably.

I also improved the audio input pipeline:

- I stopped relying on the wrong default input device
- I forced the assistant to use the real reSpeaker microphone
- I checked supported sample rate
- I improved the speech start and end detection
- I reduced unnecessary repeated transcription passes
- I changed the transcription flow to prefer auto first and then Polish only if needed

This made the assistant much more usable. It is still not perfect yet, but it is now much closer to a real working bilingual desk assistant.

Current known limitation:
The assistant now understands commands much better, but language response selection is still not fully stable. Sometimes I ask something in English and it answers in Polish, and sometimes the opposite happens. So recognition is now much better, but response language behaviour still needs more refinement.


---

## Conversation and language routing update

I upgraded the assistant from a basic command prototype into a more structured bilingual conversation system.

The main goal of this update was to make the assistant feel more natural and more consistent during real speech interaction.

### Main behaviour I wanted
I wanted the assistant to follow these rules:

- if I speak Polish, it should answer in Polish only
- if I speak English, it should answer in English only
- it should not mix Polish and English in one answer
- it should not ask extra questions about showing information on the screen unless I explicitly ask for that
- it should ignore keyboard typing, claps, chair movement, and similar non-speech sounds
- it should handle memory and reminders more reliably
- it should introduce itself as **NeXa**

### Updated conversation flow
The command flow is now more strict than before.

1. audio is captured from the microphone
2. non-speech noise is filtered more aggressively
3. Whisper transcription is checked in `auto` mode and, when needed, compared with forced Polish transcription
4. the assistant decides the language of the current command
5. the command is parsed into an intent
6. the correct handler is called
7. the assistant replies in the same language as the command
8. OLED output is shown only when the command explicitly asks to show something

### Important design changes

#### Language control
Language selection was tightened so that the reply language is linked to the current command, not only to previous assistant state.

This was needed because earlier versions could:
- answer in English after a Polish command
- answer in Polish after an English command
- keep the wrong language after a noisy or partial transcript

#### Whisper transcript selection
The speech input layer was improved so that short Polish commands are less likely to be replaced by an English auto-transcript.

This matters a lot for commands such as:
- `jak możesz mi pomóc`
- `jak się nazywasz`
- `pokaż mi godzinę`
- `zapamiętaj, że klucze są w kuchni`
- `usuń klucze z pamięci`
- `przypomnij mi za 10 sekund...`

#### Non-speech filtering
I added stronger filtering for microphone input so the assistant can ignore:
- keyboard typing
- claps
- desk hits
- chair movement
- similar short noise events

The assistant should stay silent in these cases instead of saying that it did not understand.

#### Memory reliability
The memory flow was improved so that short broken fragments are no longer saved as facts.

This was important because earlier voice cuts could create bad entries such as:
- `klucze -> w`

The memory handlers now reject obviously incomplete values and ask for a clearer sentence instead.

#### Reminder reliability
Reminder data was extended so that each reminder stores its language.

This means a reminder created in Polish should later trigger in Polish, and a reminder created in English should later trigger in English.

#### Screen behaviour
The old behaviour that asked whether information should also be shown on the screen was removed from the main conversation flow.

The assistant now follows a simpler rule:
- normal question -> speak only
- explicit `show / pokaż / display` command -> speak and show

#### Identity and branding
The assistant identity was updated to **NeXa**.

I also adjusted the self-introduction logic so that:
- `What is your name?` / `Jak się nazywasz?` gives only the name
- `Who are you?` / `Kim jesteś?` gives the fuller identity answer

### Files mainly affected by this architecture update
This improvement mainly changed the behaviour of:

- `main.py`
- `modules/core/assistant.py`
- `modules/core/language.py`
- `modules/io/whisper_input.py`
- `modules/io/voice_out.py`
- `modules/parsing/intent_parser.py`
- `modules/core/followups.py`
- `modules/core/handlers_system.py`
- `modules/core/handlers_time.py`
- `modules/core/handlers_memory.py`
- `modules/core/handlers_reminders.py`
- `modules/core/responses.py`

### Result
After this update, the assistant is closer to the premium behaviour I wanted:
- better bilingual control
- better command routing
- cleaner memory behaviour
- stronger speech-only focus
- simpler OLED interaction
- clearer assistant identity

