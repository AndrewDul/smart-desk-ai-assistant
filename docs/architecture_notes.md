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


---

## 10. Premium core stabilisation update

During the latest development stage, the assistant architecture was stabilised around a faster and cleaner local runtime model.

The main design decision was to stop treating the assistant as a rigid command parser and instead move toward a hybrid local companion architecture.

The current design now separates:

- fast action execution
- natural conversation handling
- mixed support flows
- short-term conversation continuity
- runtime diagnostics
- modular future expansion

This was done to support a more premium user experience on Raspberry Pi 5 without forcing every interaction through a heavy language model.

The current priority is now clearly:

- speed
- runtime stability
- reliable voice loop
- better post-STT intent understanding
- better bilingual consistency
- cleaner modular architecture
- future readiness for vision integration

---

## 11. Runtime architecture redesign

The runtime is no longer centered around a single older assistant logic file.

A more structured composition-root approach is now used.

### `modules/runtime_builder.py`
This module now acts as the runtime composition root.

Its responsibilities include:
- constructing the parser
- constructing the semantic router bridge
- constructing the dialogue layer
- constructing the reminder manager
- constructing the timer service
- resolving the voice input backend
- resolving the voice output backend
- resolving the display backend
- reporting runtime backend status honestly

This is an important architectural improvement because the assistant core no longer needs to instantiate every dependency itself.

### `modules/core/assistant.py`
The current assistant coordinator is now the main runtime shell.

Its responsibilities include:
- loading runtime services from the runtime builder
- managing pending follow-ups
- managing pending confirmations
- coordinating action vs conversation routes
- running the reminder background loop
- storing recent conversation turns
- executing response streaming plans
- maintaining session state and user profile state

This makes the project more maintainable and much easier to extend safely.

---

## 12. Speech input architecture update

The speech input path changed significantly.

The project no longer depends on the earlier Vosk-first direction and is also no longer centered only around the older Whisper path described earlier in the notes.

The current preferred path is:

- `faster-whisper`
- `silero-vad`
- `onnxruntime`

This was chosen because it gives a better balance between:
- speed
- quality
- bilingual usability
- realistic Raspberry Pi performance

### Current speech input behaviour
The voice input layer now:
- records from the configured microphone
- uses VAD-based speech onset and speech ending
- supports device selection by name
- supports lighter low-latency settings
- supports debug mode for troubleshooting
- returns transcript text to the assistant runtime

### Important practical lesson
A major real-world issue appeared when the runtime listened to the wrong audio device.

The assistant could start correctly and look healthy, but still fail to hear speech because it was listening to the system default input instead of the real microphone array.

This was solved by explicitly targeting the `reSpeaker` microphone path in runtime settings.

This is an important design lesson:
in embedded voice systems, a healthy startup does not automatically mean the correct microphone path is active.

---

## 13. Voice output architecture update

The voice output layer also changed direction.

The project is no longer described mainly as an `espeak-ng` assistant.

The current preferred output path is now:

- `Piper`

This change was made because the earlier speech output was too robotic for the intended premium assistant feel.

### Current voice output design
The speech output layer now supports:
- bilingual output
- language-dependent voice selection
- local voice playback
- more realistic preparation for future premium TTS quality

Fallback system tools may still exist in the runtime path for degraded environments, but the main architectural direction is clearly Piper-first.

---

## 14. Semantic routing architecture update

A major architectural improvement was the move from mostly parser-driven routing into a more layered semantic routing model.

The assistant now uses a newer routing direction built around:

- `modules/nlu/semantic_router.py`
- `modules/nlu/semantic_companion_router.py`
- `modules/nlu/semantic_intent_matcher.py`
- `modules/nlu/utterance_normalizer.py`

### Current routing model
The runtime now distinguishes between:

- action route
- conversation route
- mixed route
- unclear route

This is important because not every spoken input should be treated the same way.

Examples:

### Action route
Used for:
- timer commands
- reminder commands
- memory commands
- help
- status
- shutdown / exit
- time / date / day / year

### Conversation route
Used for:
- support-style interaction
- humour
- riddles
- selected knowledge questions
- natural small talk

### Mixed route
Used when the assistant should:
- understand a support-style statement
- answer naturally first
- then suggest a useful next action such as focus, break, or reminder

This architecture is much closer to the final project goal of a companion assistant rather than a static voice menu.

---

## 15. Dialogue architecture update

The dialogue layer has now become its own more meaningful architectural area.

### `modules/services/companion_dialogue.py`
This module now has a stronger role in the system.

Its responsibilities include:
- deterministic support replies
- deterministic humour replies
- deterministic riddle replies
- deterministic simple fact replies
- selected direct knowledge explanations
- response plan construction
- display title and line preparation
- optional use of the local LLM layer when useful

This means the project is no longer built only around commands plus canned answers.  
It now has an actual dialogue-oriented layer.

### `modules/services/local_llm.py`
A local optional LLM service was added for richer replies where useful.

The current direction supports:
- `llama-cli`
- `llama-server`

Important design decision:
the local LLM is optional and should not be used for every single interaction.

This is deliberate, because the project priority is still:
- fast local runtime
- strong practical tool handling
- realistic Raspberry Pi performance

The LLM should add value where needed, not slow down everything.

---

## 16. Response streaming architecture update

The runtime now includes a dedicated response streaming execution layer.

### `modules/services/response_streamer.py`
This module is responsible for:
- executing response plans
- splitting spoken output into chunks
- preserving quick acknowledgement-first behaviour
- generating display summaries
- improving perceived response speed

This is not yet full token-by-token model streaming.

However, it is an important architectural step because the assistant now has a streaming-first execution direction instead of a single monolithic response dump.

This supports a more premium interaction feel.

---

## 17. Short-term conversation continuity update

The assistant now includes a proper short-term conversation memory layer.

### `modules/services/conversation_memory.py`
This service stores:
- recent user turns
- recent assistant turns
- lightweight metadata
- trimmed conversation context

Its responsibilities include:
- keeping recent context lightweight
- avoiding duplicate turns
- trimming long low-value turns
- building recent context blocks for dialogue and local LLM use

This architectural update is important because the assistant now has basic recent conversational continuity instead of reacting as isolated command events.

---

## 18. Continuity integration across handlers

Another major improvement was that assistant replies from practical handlers are now integrated into recent conversation memory as well.

This applies across:
- system handlers
- time handlers
- memory handlers
- reminder handlers
- timer handlers
- focus handlers
- break handlers
- follow-up handlers

This means the assistant now has better continuity not only during conversation replies, but also after practical actions.

That is an important step toward the intended companion-like behaviour.

---

## 19. Startup diagnostics and health architecture update

The runtime diagnostics layer was improved significantly.

### `modules/system/system_health.py`
This module now performs lightweight health checks for:
- settings
- project directories
- voice input stack
- voice output stack
- display config
- optional local LLM runtime config

### Startup summary
The startup sequence now also reports a clearer distinction between:
- healthy runtime
- degraded runtime
- fallback runtime
- disabled components

This is important for realistic embedded deployment because a system may still run while some parts are only partially available.

The architecture now reflects that more honestly.

---

## 20. Configuration architecture update

The project now depends more clearly on config-driven runtime behaviour.

### `config/settings.json`
This is now the main runtime configuration file.

### `config/settings.example.json`
This now reflects the real current architecture more accurately.

The configuration now covers:
- voice input engine and tuning
- microphone selection
- voice output engine and model paths
- display configuration
- timer defaults
- streaming settings
- local LLM configuration
- logging
- system shutdown policy

This is an important improvement because the project is now more reproducible and less dependent on hidden manual assumptions.

---

## 21. Current practical architecture summary

The current NeXa architecture can now be described as:

a modular, offline-first, bilingual desk companion runtime for Raspberry Pi 5, built around:

- explicit action parsing
- semantic routing
- deterministic dialogue logic
- optional local LLM support
- response streaming
- short-term conversation memory
- local reminders
- local memory
- timer, focus, and break tools
- display output
- startup diagnostics
- runtime configurability

This is much stronger than the earlier prototype architecture.

It also gives a much better foundation for:
- final report writing
- viva explanation
- testing
- future expansion into camera / desk presence / activity context

---

## 22. Updated current limitations

The project is now much stronger, but several limitations still remain.

Current architectural limitations include:
- no full token-level streaming yet
- no camera pipeline integrated yet
- no desk presence logic yet
- no activity recognition yet
- local LLM remains optional and constrained by Raspberry Pi performance
- conversation quality is improved but still not final
- some documentation files still needed alignment with the new runtime architecture

---

## 23. Updated next architectural direction

The next recommended direction is:

### Short term
- preserve the now-working voice loop
- keep runtime stable
- continue improving perceived response speed
- improve runtime documentation and troubleshooting quality
- keep bilingual behaviour consistent

### Medium term
- improve richer knowledge responses
- improve the practical use of the optional local LLM layer
- refine mixed-route behaviour further

### Later
- integrate vision carefully
- add desk presence and light context awareness
- extend the assistant toward a more complete local companion model

---

## 24. Updated architectural conclusion

At this stage, the assistant is no longer only a basic Raspberry Pi command prototype.

It has now evolved into a more serious modular assistant core with:

- layered routing
- handler-based tool execution
- cleaner runtime composition
- better continuity
- better bilingual support
- streaming-oriented response execution
- stronger embedded realism

This creates a much better architectural base for the final project and for future premium extensions.


## 25. Storage and system rebuild update

I changed the main system storage from microSD to SSD.

This was an important practical upgrade for the project because I wanted a more stable and more realistic runtime base for NeXa. I did not want to continue building a premium assistant on top of a weaker temporary setup.

### What I changed
I:
- moved the main project workflow to SSD
- installed the system again from scratch
- updated the system packages
- installed the required Python and runtime dependencies again
- rebuilt the assistant environment on the new storage path

### Why this matters
This change improved the practical development foundation in several ways:
- better storage reliability
- cleaner rebuild of the runtime environment
- less risk of old package drift
- better long-session development stability
- better base for a premium embedded assistant

This was not only a hardware change. It also became a clean reset point for the software stack.

---

## 26. Wake-word architecture update

The wake flow was moved closer to a real assistant architecture.

Earlier, the project depended too much on speech transcription during standby. That approach worked only as a transition step, but it was not good enough for the premium target.

### Earlier wake behaviour
Earlier, the wake path still depended on a transcription-first approach:
- capture short audio
- transcribe it
- decide whether it sounded like the wake word

That was useful for testing, but it added too much delay and did not feel like a real wake-word product.

### New wake direction
I introduced a dedicated local wake-word path and separated standby wake detection from the full command transcription path.

The intended flow is now:
- standby
- dedicated wake detection
- wake acknowledgement
- active listening window
- full STT only after wake

This is a much better product direction because it reduces unnecessary processing during standby and creates a cleaner interaction model.

---

## 27. Custom local wake-word model for "NeXa"

I trained a custom local wake-word model for the project so that the assistant could react to "NeXa" through a dedicated wake gate instead of relying only on full transcription.

### Tools and workflow I used
I used:
- `openWakeWord`
- Google Colab for model training
- a custom target phrase set to `nexa`
- `piper-sample-generator` for sample generation
- the exported ONNX wake model saved as:
  - `models/wake/nexa.onnx`

### Why I used this approach
I wanted the wake system to stay:
- local
- lightweight
- cheaper to run than full STT in standby
- better aligned with a real premium voice assistant design

### Practical result
The project now has a real custom wake model that can be used by the dedicated wake gate.

That means the assistant architecture is no longer only:
- standby + short transcription guess

It now moves toward:
- standby + dedicated wake detector + full STT only after wake

This is a major architectural improvement for the premium direction of the project.

---

## 28. Current voice interaction architecture state

The current practical voice architecture is now split into two roles:

### Wake layer
The wake layer is responsible only for detecting the assistant wake word.

In the current direction, this layer uses:
- `openWakeWord`
- the custom `nexa.onnx` wake model
- a dedicated gate in:
  - `modules/io/openwakeword_gate.py`

### Command layer
After wake, the normal assistant command path still uses:
- `faster-whisper`
- VAD-based speech capture
- bilingual command handling
- the main routing and assistant logic

### Why this split matters
This split is important because it is closer to how a real product should behave:
- lighter standby
- clearer wake flow
- less wasted processing outside active interaction
- better base for future premium tuning

It is also a much better foundation for the next stages:
- echo protection
- better interruptibility
- faster command lane
- more polished conversation flow

---

## 29. Current architectural priority after wake-word integration

After getting the dedicated wake path working, the next priority is no longer basic wake detection.

The next priority is interaction quality.

### Current top priorities
The most important next architectural tasks are:
- protect the assistant from hearing its own TTS output
- return to standby correctly after asynchronous speech such as timer completion
- improve fast command handling
- improve the premium feeling of the interaction loop

### Why this is now the right priority
At this stage, the project already has:
- a modular runtime
- a wake path
- a command path
- bilingual speech handling
- reminders, memory, timer, and display behaviour

The biggest remaining difference between "working" and "premium" is now interaction polish rather than basic capability.

That is the current direction of the project.


---

## 9. Current premium voice architecture direction

At this stage I moved the project away from a simple command prototype and much closer to a premium voice product structure.

The main goal of the current architecture is not only to make NeXa work, but to make it feel stable, predictable, fast, and ready for future expansion.

### 9.1 State-based voice session model

I now treat the assistant as a state-driven voice system.

The main voice states are:

- `standby`
- `wake_detected`
- `listening`
- `transcribing`
- `routing`
- `thinking`
- `speaking`
- `shutdown`

This makes the flow easier to reason about and reduces hidden behaviour.

Instead of treating the assistant like one long loose loop, I now treat each stage as a different part of the interaction lifecycle.

This is important because I want NeXa to behave like a real product, not like a collection of separate scripts.

### 9.2 Dedicated wake path

The standby path is now separated from the full speech-to-text path.

I use:

- `openWakeWord`
- custom local wake model: `models/wake/nexa.onnx`

This means standby no longer depends only on full transcription-first behaviour.

The dedicated wake gate is lighter and more product-like.

The intended flow is now:

1. standby
2. dedicated wake detection
3. short wake acknowledgement
4. active listening window
5. full STT and command handling

This is a much better base for premium interaction than keeping full STT active all the time.

### 9.3 Full STT only after wake

After wake, the assistant uses the normal transcription path for real commands.

This keeps the system more efficient and makes the interaction model cleaner:

- wake detection is lightweight
- real command understanding starts only after wake
- normal conversation still supports Polish and English

This separation is important for both performance and predictability.

### 9.4 Audio coordination and self-hearing protection

One of the most important improvements was adding an audio coordination layer.

The problem was that TTS, wake detection, and full STT were working, but they were not coordinated strongly enough at runtime.

Because of that, NeXa could sometimes react to her own voice, especially after:
- timer finished
- reminders
- system replies
- follow-up speech

To improve this, I introduced a dedicated audio coordination service.

This layer now:
- knows when assistant playback starts
- knows when assistant playback ends
- keeps a short post-speech shield
- tells wake and STT input layers when input should stay blocked

This gave me a much cleaner separation between:
- assistant output
- user input

It also reduced self-hearing and made the whole voice loop more stable.

### 9.5 Async notification behaviour

I also separated normal conversation turns from async notification turns.

This matters for things like:
- timer finished
- reminder due
- break finished
- focus finished

These events are not the same as a live user-led conversation turn.

So I added a dedicated async notification delivery rule.

When NeXa speaks an async notification, I now treat it as:
- notification output
- not as an open follow-up conversation

This means the assistant:
- clears old pending interaction context
- speaks the message
- returns to standby after the message

This is important because I do not want background notifications to leave the assistant in a half-open conversational state.

### 9.6 Fast command lane

I added a lightweight fast command lane for direct system-style commands.

This lane is meant for actions such as:
- time
- date
- day
- month
- year
- timer
- focus
- break
- memory actions
- reminder actions
- assistant identity
- exit and shutdown

The point of this lane is simple:
I do not want every command to travel through the heavier dialogue path.

The fast lane gives me:
- quicker response
- cleaner routing
- better override behaviour
- less unnecessary conversational overhead

It also helps with another important rule:
a clear new command should beat an older follow-up.

### 9.7 Thinking acknowledgements

For slower dialogue paths, I added delayed thinking acknowledgements.

If the assistant needs more time before replying, NeXa can now say a short natural phrase such as:
- `Just a moment.`
- `Give me a second.`
- `I’m checking.`
- `Let me think.`

I only use this for slower dialogue-style routes.

I do not use it for fast direct commands because I do not want to add fake delay to actions that should feel instant.

This improves perceived responsiveness and removes dead silence during slower reply generation.

### 9.8 Interrupt foundation

I also started building a cleaner interrupt model.

At the current stage, the safest working version is wake-based interruption.

That means:
- when NeXa is speaking or thinking
- I can use the wake path again
- the old output can be interrupted
- a new command can take priority

This is safer than trying to let the assistant listen freely during her own TTS in the same local audio setup.

It is not the final interrupt model yet, but it is a strong and practical step toward more premium barge-in behaviour.

### 9.9 Why this architecture matters

These changes matter because I want NeXa to become:

- predictable
- easy to interrupt
- clear about what state she is in
- less likely to react to the wrong sound
- faster on simple actions
- calmer during background events
- easier to extend later

This architecture also prepares the project for later additions such as:
- AI HAT+ 2
- camera and vision
- stronger local conversation models
- better streaming
- richer face and eye behaviour

At this point the project is no longer just a basic assistant loop.
It is becoming a structured voice runtime that I can keep improving in a controlled way.


## 30. Runtime structure cleanup and folder organisation update

During this stage I cleaned the project structure further so the runtime became easier to follow.

The main goal was not to redesign everything again, but to make the project more readable, more organised, and safer to extend. I wanted the codebase to feel less mixed and more deliberate.

### What I improved

I continued separating the project into clearer areas with more explicit responsibility.

The runtime is now easier to read because the main parts are grouped by role instead of being left in a flatter mixed structure.

The practical direction now looks more like this:

- `modules/core/`
  - main assistant coordination
  - session state
  - high-level runtime flow

- `modules/runtime/`
  - runtime builder
  - backend composition
  - startup health and backend status

- `modules/devices/`
  - audio input
  - audio output
  - wake handling
  - display handling

- `modules/features/`
  - timers
  - reminders
  - memory
  - conversation support services

- `modules/understanding/`
  - parsing
  - routing
  - dialogue and intent interpretation

- `modules/shared/`
  - config
  - logging
  - lower-level shared helpers

This made the project easier to reason about because hardware paths, assistant logic, feature logic, and runtime composition are now more clearly separated.

### Why this helped

This cleanup improved the architecture in a practical way:

- the runtime is easier to trace
- backend ownership is easier to understand
- it is easier to see where wake, STT, TTS, and display logic belong
- the project is easier to explain during development and documentation work
- future refactors are safer because responsibilities are less mixed

Another useful improvement is that the runtime now follows a more deliberate composition flow instead of letting too much setup happen inside one assistant file.

That gives me a cleaner mental model of the system:
- builder creates runtime parts
- core assistant coordinates them
- device modules talk to hardware
- feature modules handle assistant tools
- understanding modules decide what the user meant

### Current limitation

Even after this cleanup, I still have some files that are too large.

The structure is better now, but some important files still carry too much logic in one place. This means the architecture is cleaner than before, but not fully finished yet.

The biggest remaining structural problem is not folder layout anymore.  
The biggest remaining structural problem is oversized files.

I still need to split some of the larger files further so that:
- each file has one clearer job
- debugging becomes easier
- testing becomes easier
- future changes do not create new mixed logic again

### Current conclusion

This was a useful architecture step.

I made the project more organised, more readable, and more professional internally.  
The folder structure is now better aligned with the real runtime roles.

At the same time, I can already see the next cleanup task clearly:
I still need to break down the biggest files into smaller units so the internal structure becomes as strong as the outer folder structure.


## 31. Large file breakdown and readability improvement

In this stage I also broke down the biggest files into smaller modules.

I did this because some parts of the project were becoming too heavy in one place. Even when the folder structure looked better, a few large files still made the code harder to read, harder to debug, and harder to change safely.

So I split the larger files into smaller parts with clearer jobs. This made the project easier to follow and easier to work on. It also reduced the risk of making one change that affects too many unrelated parts.

The main reason for this change was simple:
I wanted the code to be more readable and easier to improve later.

This breakdown also makes future work easier because:
- I can find logic faster
- I can test changes more safely
- I can debug problems more easily
- I can extend features without making the same files too large again

This was an important cleanup step for the internal quality of the project.  
The outer folder structure is now clearer, and the inside of the bigger modules is also in a better state than before.

### Main files I broke down
The main large files I worked on included:

- `modules/core/flows/action_flow.py`
- `modules/devices/audio/input/faster_whisper/backend.py`
- `modules/core/flows/pending_flow.py`
- `main.py`
- `modules/core/assistant.py`
- `modules/understanding/dialogue/llm/local_llm.py`
- `modules/understanding/parsing/parser.py`
- `modules/devices/audio/input/whisper_cpp/backend.py`
- `modules/runtime/builder.py`
- `modules/understanding/routing/companion_router.py`
- `modules/understanding/dialogue/companion_dialogue.py`
- `modules/devices/audio/output/tts_pipeline.py`
- `modules/runtime/health.py`
- `modules/presentation/response_streamer.py`
- `modules/devices/audio/input/wake/openwakeword_gate.py`
- `modules/core/flows/command_flow.py`
- `modules/devices/display/display_service.py`
- `modules/core/session/voice_session.py`
- `modules/core/flows/dialogue_flow.py`
- `modules/runtime/contracts.py`
- `modules/shared/config/settings.py`
- `modules/features/reminders/service.py`
- `modules/core/flows/notification_flow.py`

### Result
After this change, the codebase is more modular, easier to read, and easier to change.  
This should also make future refactors safer, because the logic is no longer packed into a few oversized files.

## 32. AI HAT+ 2, Hailo-backed local LLM, pan-tilt platform, and LCD hardware expansion

During this stage I pushed the project further from a voice prototype toward a more physical and modular assistant system.

The biggest practical changes in this stage were:
- continuing the breakdown of oversized files into smaller modules
- mounting and integrating the AI HAT+ 2
- moving the local LLM direction toward a Hailo-backed backend model
- adding pan-tilt platform control
- mounting the LCD on the moving platform
- adding voice-controlled movement commands
- carrying out camera-related hardware tests
- improving runtime behaviour around wake, voice input fallback, and audio output problems

### Large file split continuation

After the earlier folder cleanup, I continued breaking down the biggest files into smaller parts.

This was important because some core runtime files were still carrying too much logic in one place. The main goal was to keep the architecture readable and scalable while adding more hardware and backend complexity.

This continued split was especially important for:
- runtime builder logic
- assistant flow coordination
- parser logic
- local LLM runtime logic
- display handling
- wake handling
- reminder service structure

This made the project easier to reason about while the system was growing into a more advanced hardware-assisted assistant.

### AI HAT+ 2 and Hailo-backed backend direction

A major architectural change in this stage was the move toward running the optional local LLM through a dedicated backend path connected with the AI HAT+ 2 workflow.

The important design decision here is that NeXa should not treat the accelerator as random low-level hardware attached directly to the assistant logic. Instead, the project now moves toward a cleaner architecture where the assistant talks to a dedicated local backend service and receives model responses through a controlled runtime boundary.

This is a better product direction because it:
- keeps assistant logic cleaner
- separates inference serving from assistant orchestration
- makes backend health easier to diagnose
- gives a better foundation for startup checks and future deployment flow

### Practical Hailo-related lesson

This stage also showed an important real-world lesson:
getting Hailo working is not only a code problem.

The practical work included:
- installation-related problems
- backend connection problems
- checking whether the backend was really reachable from the main assistant runtime
- distinguishing between model logic problems and backend availability problems

This became an important architecture note because the assistant can appear healthy while the Hailo-backed local LLM path is still unavailable or only partially connected.

### Pan-tilt platform architecture update

The hardware architecture was expanded with a pan-tilt platform.

The project now includes:
- pan / tilt hardware control
- platform motion logic
- dedicated motion test scripts
- integration of movement behaviour with the assistant runtime direction

This is important because the assistant is no longer only a voice-and-screen prototype.  
It now also has a physical motion layer that can be controlled and tested.

### Voice-controlled movement

Another important update in this stage was adding spoken control for directional movement.

The assistant can now interpret movement commands such as:
- left
- right
- up
- down

This means the voice interaction layer is now connected not only to reminders, memory, timers, and conversation, but also to physical hardware motion.

That is an important architectural step because it proves the assistant is growing into a more embodied system rather than staying only a software shell.

### LCD mounted on the moving platform

The display architecture also became more physical in this stage.

The LCD was mounted on the moving platform, which means visual output and motion behaviour now exist together as one combined hardware presentation layer.

This is important because the project is moving toward synchronised behaviour across:
- voice
- visual output
- mechanical movement

That is much closer to the premium assistant direction than keeping these parts separate.

### Expressive hardware testing direction

A useful result of this stage is that the project now has a clearer path toward combined behaviour testing.

This means:
- platform movement can be tested directly
- the LCD can be used during motion-related tests
- future behaviour scripts can combine eye states, visual feedback, and movement patterns in one hardware flow

This gives a much better base for future premium interaction design.

### Camera testing status

Camera-related testing was also carried out during this stage, but the important architectural point is that this should still be treated as a preparation and validation phase rather than a fully finished production vision runtime.

In practical terms:
- camera work has started at the testing level
- hardware validation has moved forward
- the project is closer to vision integration
- but the camera path should still be described as an in-progress integration area unless a full production runtime service is added and stabilised

### Voice input fallback lesson

Another important practical issue in this stage was the case where the assistant stopped behaving like a real voice assistant and instead acted as if it wanted typed input.

This happened when the real voice path failed or degraded and the runtime fell back to text input behaviour.

From an architecture point of view, this matters because it shows that:
- startup success is not enough
- runtime health must reflect the real active input path
- voice failure must not silently look like normal assistant behaviour

This became an important product lesson for NeXa:
a premium assistant must report degraded runtime truthfully and should avoid misleading fallback behaviour.

### Speaker and output-path lesson

I also had to deal with speaker-related runtime confusion.

This was important because speech output problems are not always the same as TTS generation problems. In practice, the project had to treat:
- speech synthesis
- playback
- system audio routing

as separate parts of one output pipeline.

That became another useful architecture lesson:
the assistant may generate a reply correctly while still failing to produce real audible output.

### Wake spam and wake-loop hardening

Another practical issue during this stage was unstable wake behaviour, including repeated wake-like triggering and noisy wake-loop behaviour.

This matters architecturally because the wake path is not only a detection model problem. It is also a runtime control problem involving:
- microphone ownership
- filtering of short speech
- coordination with assistant playback
- post-reply listening behaviour
- threshold and cooldown tuning

This stage pushed the project further toward a cleaner premium wake model rather than a fragile experimental wake loop.

### Result of this architecture stage

At the end of this stage, the project became stronger in several important ways:
- the codebase stayed modular while complexity increased
- the AI HAT+ 2 and Hailo-backed backend direction became part of the architecture
- the assistant gained a physical motion layer
- the LCD became part of a moving hardware presentation setup
- voice commands expanded into motion control
- camera preparation moved forward
- troubleshooting knowledge around Hailo, speaker output, fallback input, and wake stability became much more mature

This stage was important because it moved NeXa further away from a software prototype and closer to a real modular embedded assistant system.



## 33. NeXa 2.0 product direction and target runtime lock

During the latest development stages, the project direction was tightened around **NeXa 2.0** as a premium local-first assistant rather than a general student prototype.

This is an important architectural shift.

Earlier stages were focused on proving that:
- voice input works
- voice output works
- reminders and memory work
- display output works
- wake can work locally
- the runtime can be reorganised safely

The current direction is different.

The project is now being shaped as a premium embedded assistant with:
- fast wake
- fast built-in commands
- always-on local AI backend
- streaming-first response flow
- stronger state handling
- clearer system health reporting
- measurable premium behaviour
- cleaner hardware boundaries
- modular code ready for long-term extension

### Current target architecture layers

The target NeXa 2.0 architecture is now understood more clearly as:

- `runtime`
  - startup
  - service composition
  - health checks
  - state reporting
  - shutdown and recovery

- `audio`
  - capture
  - wake
  - VAD / endpointing
  - playback coordination
  - self-hearing protection
  - TTS execution

- `ai`
  - STT
  - local LLM backend access
  - routing
  - later vision / VLM support

- `skills`
  - timer
  - focus
  - break
  - reminders
  - memory
  - self-introduction
  - system status
  - later mobility-oriented actions

- `session`
  - active window
  - follow-up handling
  - confirmation handling
  - interruption control
  - short-term continuity

- `presentation`
  - display overlays
  - startup cues
  - acknowledgement behaviour
  - later combined motion + expression presentation

- `persistence`
  - settings
  - profiles
  - reminders
  - memory
  - traces
  - benchmarks
  - runtime state snapshots

### Practical system roles

The practical system role split is now much more deliberate:

- **Raspberry Pi 5**
  - orchestration
  - audio coordination
  - runtime control
  - skill execution
  - display and presentation coordination
  - persistence
  - hardware integration

- **AI HAT+ 2**
  - accelerated local AI direction
  - primary heavy local inference backend path
  - later stronger STT / LLM / VLM use when stable enough

This is important because the project is no longer being shaped as one Python assistant loop with random hardware attached.
It is now moving toward a more realistic embedded product architecture with cleaner system boundaries.



## 34. Observability, premium validation, and release-gate architecture

Another major architectural step was the move toward explicit runtime observability and premium validation.

The system is no longer treated as “working” only because it starts and answers.  
Instead, the project now uses a more product-like view of runtime truth.

### Runtime truth model

The runtime now needs to report more honestly whether the system is:

- healthy
- degraded
- limited
- blocked
- failed
- stopped

This matters because a voice assistant can:
- start
- print logs
- show a screen
- even answer sometimes

while still being in a degraded state that is not acceptable for a premium product.

### Benchmark and validation direction

The project now includes stronger benchmark and validation thinking around:

- wake latency
- STT latency
- route-to-first-audio latency
- local LLM first chunk timing
- response first audio timing
- turn completion quality
- segment coverage across skill and LLM turns
- premium release gate decisions

This means the benchmark layer is no longer just a debug extra.
It is becoming part of the product-quality architecture.

### Why this matters

This architectural direction is important because it changes how the project is judged.

The assistant should not be described only as:
- can answer
- can wake
- can speak

It should now also be described as:
- measurable
- diagnosable
- benchmarkable
- release-gated
- honest about degraded states

This is a major upgrade in engineering maturity.


## 35. Camera Module 3 Wide and embodied presentation hardware update

The hardware setup moved further toward an embodied assistant form.

The project now includes the **Raspberry Pi Camera Module 3 Wide** as part of the mounted hardware stack.

### Current camera status

At the current stage, the camera should be described as:

- physically integrated into the hardware direction
- detected successfully by Raspberry Pi camera tools
- validated at the hardware level
- suitable for continued vision integration work
- not yet described as a fully finished production vision runtime

This distinction matters.

Hardware validation is already real progress, but it is not the same as saying that a complete vision service is already finished.

### Presentation stack direction

The project now moves toward a combined presentation stack rather than isolated output channels.

The practical presentation direction now includes:

- spoken output
- LCD visual feedback
- pan-tilt movement
- camera-ready embodiment
- later mobility-aware expression and response

This is important because the assistant is no longer only:
- a speaker
- a microphone
- a screen

It is becoming a more embodied system where:
- voice
- display
- mechanical movement
- future camera awareness

can become part of one coordinated assistant behaviour model.


## 36. Mobile base integration - Waveshare UGV02

Today the project moved into a new hardware stage with the mounting of the mobile base:

**Waveshare UGV02 6-wheel 4WD Off-Road UGV Kit (ESP32 Driver)**

This is an important milestone because NeXa now has a real chassis layer rather than only pan-tilt and static desk presence.

### Architectural role of the mobile base

The mobile base should not be treated as raw motor logic directly embedded into assistant flow code.

The correct architecture direction is:

- the **UGV02 ESP32 driver board** owns the low-level chassis control
- the **Raspberry Pi** owns high-level orchestration and later movement intent
- communication between the Pi and the base happens through a clean control boundary

### Current communication boundary

The practical boundary currently used is:

- USB-C connection from the mobile base to Raspberry Pi
- serial device path such as:
  - `/dev/ttyACM0`
- JSON control messages sent from Raspberry Pi to the UGV02 controller

This is an important design choice because it matches the overall NeXa architecture philosophy:
assistant logic should talk to dedicated hardware control boundaries instead of mixing high-level behaviour with low-level motor details.

### Current mobility test direction

The current mobility stage is still a validation and calibration stage.

At this stage, the project now includes manual hardware-oriented tests under:

- `tests/hardware/ugv02/`

These tests are used to validate:
- serial communication with the chassis
- safe desk movement
- forward / backward movement
- rotation behaviour
- repeatable command flow from Raspberry Pi

### Current motion control lesson

A key practical result from this stage is that the mobile base responds correctly through the serial boundary when driven with the working streamed control path.

The current working movement direction uses:
- repeated streamed movement commands
- explicit stop commands
- small calibration-oriented motion segments

This is important because it proves:
- the Pi can see the UGV02
- the Pi can command the UGV02
- the base can move under software control from the NeXa project environment

### Important limitation

At the current stage, the mobility tests should still be described as:

- manual
- calibration-oriented
- desk-safe
- open-loop

This means they are useful for hardware validation, but they are not yet the final mobility runtime.

The final mobility direction should later move toward:
- a dedicated transport / chassis service
- closed-loop motion where practical
- better calibration and safety policy
- cleaner integration with assistant-level movement skills



## 37. Current system state after mobility mounting

At this stage, NeXa should no longer be described as only a stationary Raspberry Pi assistant prototype.

The system now includes:

- Raspberry Pi 5 runtime orchestration
- AI HAT+ 2 integration direction
- bilingual voice interaction
- local wake-word direction
- LCD presentation layer
- pan-tilt platform
- camera hardware validation
- mobile chassis integration through UGV02
- benchmark-aware premium runtime direction

This is a major practical shift.

The assistant is now moving from:
- voice-and-screen prototype

toward:
- a modular embodied assistant platform

### Current architecture conclusion

The project is now much closer to the final intended NeXa 2.0 direction:

- premium local-first assistant
- clear runtime boundaries
- honest health reporting
- measurable interaction quality
- embodied hardware stack
- mobility integration path
- future-ready camera and AI acceleration direction

### Next recommended architecture step

The next architecture step after this point should be:

- introduce a dedicated mobility client / transport service for UGV02
- keep manual hardware tests separate from runtime logic
- later expose movement through assistant-level skills
- preserve the premium voice/runtime path while mobility is integrated
- avoid mixing direct serial motor control into high-level assistant orchestration



## 28. Battery-backed power architecture update

I clarified and validated the practical power architecture for NeXa when running from battery through the X1206 UPS rather than from a normal external USB-C power adapter.

This became important because NeXa is no longer only a desk-bound software prototype.
The project is moving toward a more embedded and battery-capable hardware platform, so the power path must be described as part of the architecture, not only as a temporary hardware detail.

### Current power direction

The current practical power direction is:

- Raspberry Pi 5 as the main compute node
- X1206 as the battery-backed UPS and power-conditioning layer
- 21700 battery cells as the energy storage layer
- SSD boot as the main system storage direction
- USB peripherals such as microphone, speaker, and other connected devices sharing the practical power budget

This means the power path is now part of the real runtime architecture.

### Important architectural insight

During validation I confirmed that the main challenge was not only battery capacity.

The more important issue was that Raspberry Pi 5 can apply a conservative USB-boot and USB-current policy when the power source is not detected like a normal 5V / 5A USB-PD supply.

This matters architecturally because:
- the system can still have enough real battery energy
- but the Pi can still behave as if the source should be treated more cautiously
- this directly affects practical runtime behaviour for SSD boot and USB-connected devices

### Architectural adjustment

To align Raspberry Pi 5 behaviour with the intended X1206 battery-backed runtime, I adopted an explicit power-policy override as part of the embedded platform design.

The validated settings are:

- `PSU_MAX_CURRENT=5000` in EEPROM
- `usb_max_current_enable=1` in `/boot/firmware/config.txt`

This is not just a random workaround.
In this project, it becomes part of the defined hardware-runtime contract between:
- Raspberry Pi 5
- the X1206 UPS path
- the battery-backed NeXa deployment model

### Why this matters

This update improves the architecture in several ways:

- it makes battery-backed boot behaviour more predictable
- it reduces the risk of Raspberry Pi 5 staying in an unnecessarily reduced USB-current policy
- it gives a cleaner path for running NeXa from battery without depending on a normal external USB-C supply
- it supports the move toward a more realistic embedded assistant platform

### Current practical interpretation

The current architecture should therefore treat the X1206 path as:

- the active battery-backed power layer
- a valid runtime direction for NeXa
- a path that requires explicit Raspberry Pi 5 power-policy configuration
- a hardware layer that still needs full-load validation as the system grows

### Current limitation

Even with the correct override, this does not create unlimited power.

The architecture still needs to respect real load limits under:
- SSD boot
- USB peripherals
- audio activity
- display usage
- future camera and mobility expansion

So the correct architectural view is:

- the policy issue is now understood
- the current configuration is valid
- the X1206 remains part of the intended battery-backed design
- future heavy-load validation is still required

### Architectural conclusion

This power update moves NeXa closer to a real embedded system architecture.

Instead of relying only on a standard desk power adapter model, the project now has a clearer battery-backed runtime direction with:
- UPS-backed operation
- SSD-backed storage
- explicit Raspberry Pi 5 power-policy control
- a more honest and realistic embedded deployment model

## 38. Intent-driven AI ownership policy for AI HAT+ 2, local LLM, and vision

This section records an important architecture decision for NeXa.

NeXa runs on Raspberry Pi 5 with AI HAT+ 2.  
This hardware is able to support both:
- local generative AI
- camera and vision workloads

That is a strong capability, but it also means NeXa must manage one shared AI resource carefully.

The main goal is not to make every AI task run at full strength all the time.  
The main goal is to make NeXa feel fast, natural, stable, and reliable.

For this product, the user experience is more important than trying to keep every heavy workload active at the same time.

### What NeXa needs in real use

NeXa does not always need the same thing.

Sometimes the user wants a fast spoken answer.  
Sometimes the user wants NeXa to look at something.  
Sometimes the user wants NeXa to quietly monitor a situation for a longer time.

These are different kinds of work.  
Because of that, NeXa should not use one fixed policy for every moment.

The right approach is:

## intent-driven ownership

This means the current user intent decides which subsystem owns the AI priority.

In simple terms:
- when the user asks a normal question, the answer path should win
- when the user asks NeXa to check or find something visually, the vision path should win
- when the user enables a monitor mode, the monitor path should stay active and efficient
- the switch between these modes should be handled by NeXa runtime, not by unrelated modules fighting over the device

This is the best fit for a premium local-first assistant.

### Why the simple "YOLO always on, pause for LLM" model is not enough

A rough design idea would be:

- keep a heavy object detector running all the time
- when the wake word is triggered, pause vision
- give the device to the LLM
- when the answer is done, resume vision

That idea is easy to understand, but it is still too rough for NeXa.

The main problems are:

#### 1. Heavy vision all the time is not the best idle state
NeXa does not need maximum object detection pressure during every idle second.

In the idle state, NeXa mostly needs:
- presence awareness
- desk awareness
- basic scene continuity
- optional object refresh when useful

That means full heavy detection all the time would waste compute, thermal headroom, and scheduling flexibility.

#### 2. Hard switching is too crude
A full stop / full resume pattern on every turn can create extra overhead and unstable behaviour.

It can increase the risk of:
- handover delays
- device busy situations
- jitter between fast follow-up turns
- more fragile error recovery
- poor smoothness during bursty interaction

#### 3. Full vision shutdown is not always desirable
There are many cases where NeXa still needs light awareness even while a response is being prepared or while a task is active.

The correct goal is not full blindness.  
The correct goal is to keep the cheap and useful parts alive while reducing only the expensive parts when needed.

### Best decision for NeXa

The best solution for NeXa is not:
- vision always wins
- LLM always wins
- everything runs at full strength all the time

The best solution is:

## one NeXa-owned AI broker with intent-driven task ownership

This means:
- one central runtime owner manages the AI HAT+ 2 path
- vision does not grab the device directly on its own
- the LLM path does not grab the device directly on its own
- NeXa runtime decides who has priority based on the current task
- heavy jobs are scheduled deliberately instead of being left to collide

This gives better responsiveness, better stability, and cleaner behaviour.

### Core principle

The core principle is:

**The current task decides who gets AI priority.**  
**Conversation tasks favour the answer path.**  
**Vision tasks favour the camera and perception path.**  
**Monitoring tasks favour efficient long-running observation.**

This is the most natural fit for NeXa.

### Single owner and scheduler-first policy

NeXa should use one clear ownership boundary for the AI accelerator path.

The preferred architecture is:
- one NeXa-owned broker or coordinator
- one process owning the main Hailo interaction when possible
- scheduler-first model sharing inside that owner
- multi-process service only if the project later becomes truly multi-process

This keeps the system simpler and reduces the risk of runtime conflicts.

In practical terms, that means:
- do not let vision manage low-level Hailo ownership by itself
- do not let the LLM path manage low-level Hailo ownership by itself
- do not hardcode device handover rules in many parts of the codebase
- keep policy decisions in one runtime layer

### What this means for NeXa behaviour

NeXa should behave differently depending on what the user is asking for.

## 1. Conversation Answer Mode

This mode is used when the user asks a normal question and expects a quick reply.

Examples:
- "NeXa, what time is it?"
- "NeXa, explain this"
- "NeXa, what is the weather like?"
- "NeXa, tell me how to fix this"

In this mode:
- the answer path gets priority
- heavy vision work can step back
- cheap background awareness may remain alive if it is harmless
- the system protects response speed and streaming smoothness

The target here is simple:
NeXa should answer quickly and sound natural.

If the user only needs an answer, heavy camera work should not slow that down.

## 2. Vision Action Mode

This mode is used when the user asks NeXa to look, find, inspect, track, or navigate.

Examples:
- "NeXa, where is my phone?"
- "NeXa, check if I am using my phone"
- "NeXa, look at the desk"
- "NeXa, go to the kitchen"

In this mode:
- the vision path gets priority
- the LLM does not need to generate a long answer first
- NeXa may give a short natural acknowledgement
- the main work goes into perception, detection, and task execution

The right pattern here is:
- short acknowledgement first
- heavy vision work second
- fuller answer after the result is known

This avoids wasting time on unnecessary generation before the task is done.

## 3. Focus Sentinel Mode

This mode is used when the user enables longer monitoring behaviour.

Examples:
- "NeXa, focus mode"
- "NeXa, watch whether I am studying"
- "NeXa, tell me if I start using my phone"

In this mode:
- the camera path stays active
- monitoring is efficient, not wasteful
- checks can be periodic or event-driven
- the LLM mostly stays quiet
- NeXa only speaks when it has a reason to speak

This mode is not about constant talking.  
It is about stable observation with low friction.

## 4. Recovery Window

After a task ends, NeXa should not immediately jump to another heavy policy in a rough way.

A short recovery window helps with:
- follow-up voice turns
- repeat visual checks
- smoother transition back to idle behaviour
- fewer unnecessary scheduling spikes

This makes interaction feel cleaner and more stable.

### Fast lane and heavy lane

For NeXa, the best runtime split is:

## Fast lane
This should stay available more often:
- frame capture
- cheap camera continuity
- basic face-based awareness
- presence state
- desk engagement state
- stabilization
- session tracking

This lane should be light, responsive, and reliable.

## Heavy lane
This should run when it adds real value:
- full object detection
- richer scene understanding
- phone object checks
- computer object checks
- other expensive model-driven analysis
- heavier LLM generation work

This split is important.

NeXa should not treat all vision as equally expensive, and it should not treat all AI work as always urgent.

### Why this helps performance

This policy helps avoid:
- slow first replies
- long first-audio delays
- unnecessary heavy idle inference
- device ownership conflicts
- thermal pressure from always-on heavy workloads
- poor behaviour during repeated mode changes

It also gives NeXa a better chance to feel:
- quick when answering
- quick when checking something visually
- calm during focus mode
- stable across long sessions

### Natural interaction matters

NeXa should not feel like a system that always tries to do everything at once.

It should feel like a smart companion that understands what the user wants right now.

That means:
- if the user asks a normal question, NeXa should answer quickly
- if the user asks for a visual check, NeXa should look first and explain after
- if the user enables monitoring, NeXa should stay quiet and only speak when needed

This behaviour is more natural and more premium than forcing the same AI policy onto every task.

### Cooling and runtime discipline

NeXa should treat thermal stability as part of system architecture, not as an afterthought.

Heavy AI workloads can increase heat and reduce runtime stability if cooling is weak.  
Because of that, sustained AI use should assume:
- proper Raspberry Pi 5 cooling
- good airflow
- careful benchmarking under realistic load
- observation of latency, temperature, and recovery behaviour

The right architecture is not only the one that works once.  
It is the one that keeps working smoothly over time.

### Final policy for this stage

The current architecture decision for NeXa is:

1. Do not treat AI HAT+ 2 as unlimited shared capacity.
2. Do not keep heavy vision inference running at maximum effort by default.
3. Do not rely on crude stop/start switching as the main control strategy.
4. Use one NeXa-owned broker to control the AI accelerator path.
5. Prefer scheduler-first coordination inside one owner process when possible.
6. Give priority to the subsystem that matches the current task.
7. Keep a cheap fast lane alive more often.
8. Run heavy AI work when it is useful, not just because it can run.
9. Use short acknowledgements before heavy visual tasks when needed.
10. Use a recovery window to avoid rough transitions and scheduling thrash.

### What this means for the roadmap

This decision leads to the following order:

1. finish real Hailo object detection integration
2. connect object-backed computer work and phone usage signals
3. add the NeXa AI broker
4. define the three main ownership modes:
   - conversation answer mode
   - vision action mode
   - focus sentinel mode
5. add the recovery window policy
6. benchmark:
   - wake latency
   - first chunk latency
   - first audio latency
   - reply smoothness
   - visual task completion time
   - thermal stability
   - long-session behaviour

### Final conclusion

The best design for NeXa is not based on a permanent winner between vision and LLM.

The best design is based on clear ownership by current intent.

NeXa should:
- answer quickly when the user wants an answer
- look quickly when the user wants a visual action
- monitor quietly when the user wants background observation
- switch between these behaviours in a controlled way

That is the architecture direction that best matches a premium local-first NeXa product on Raspberry Pi 5 with AI HAT+ 2.


## 39. Current NeXa hardware stack and embodied platform baseline

This section records the current practical hardware direction of NeXa.

NeXa is no longer only a stationary Raspberry Pi voice assistant prototype.  
The project has now moved toward a compact, premium, embodied, local-first AI assistant platform.

The current hardware direction includes compute, display, vision, movement, battery-backed power, storage, and mechanical expression.

### Current compute and AI foundation

The current main compute and AI foundation is:

- Raspberry Pi 5 16GB
- Raspberry Pi AI HAT+ 2
- SanDisk SSD 1TB

The Raspberry Pi 5 remains the main orchestration node.

Its responsibilities include:
- runtime coordination
- audio input and output coordination
- wake/STT/TTS pipeline control
- command routing
- session state
- persistence
- Visual Shell control
- hardware coordination
- future system-control and mobility orchestration

The AI HAT+ 2 remains part of the local-first AI acceleration direction.

Its intended role is to support heavier local AI workloads such as:
- local generative AI backend work
- future vision inference
- future perception and AI-broker-controlled workloads

The SanDisk SSD 1TB is now part of the serious runtime foundation.

The SSD matters because NeXa should not depend on weak or temporary storage for a premium runtime.  
It gives the system a stronger base for:
- project files
- runtime state
- models
- logs
- benchmark output
- future perception and memory data

### Current primary display direction

The project now includes:

- 8-inch HD DSI capacitive touch display
- 1280x800 display target
- touch-capable interaction direction

This display is an important hardware upgrade because NeXa is no longer intended to feel like a small debug device.

The 8-inch DSI display gives NeXa:
- a much stronger visual presence
- more space for a premium animated interface
- better readability
- better future touch interaction potential
- a better foundation for desktop docking and system-control behaviour
- a more product-like user experience

The display should be treated as the primary visual identity surface for NeXa.

Older OLED or small LCD display work remains useful as historical development context and fallback/diagnostic reference, but the current premium direction is centered on the 8-inch DSI display and the Visual Shell.

### Current vision hardware

The project now includes:

- Raspberry Pi Camera Module 3

The camera is part of the future vision and awareness direction.

At the current architecture level, it should be described as:
- physically part of the NeXa hardware stack
- intended for future local vision features
- suitable for perception, object detection, user awareness, and environment checks
- not yet treated as a fully finished production vision runtime unless the dedicated vision service is implemented and validated

This distinction is important.

Having the camera installed or validated is not the same as having a complete production camera intelligence layer.  
The final system still needs a clean vision service, perception contracts, AI broker integration, and runtime diagnostics.

### Current mechanical expression hardware

The project now includes:

- Waveshare 360° Omnidirectional High-Torque 2-Axis Pan-Tilt

This gives NeXa a physical expression layer.

The pan-tilt module is important because NeXa should not only speak and show animations.  
It should also be able to physically orient its head/display/camera direction in a controlled way.

The intended role of pan-tilt is:
- looking toward the user
- looking around
- supporting scan behaviour
- supporting future camera framing
- making the assistant feel more embodied
- improving the feeling of presence during interaction

The pan-tilt module should not be controlled directly from random assistant logic.

The preferred architecture is:
- assistant core decides intent
- a dedicated motion or device-control layer executes movement
- Visual Shell shows the matching visual state
- future vision can provide feedback for where NeXa should look

### Current mobility hardware

The project now includes:

- 6x4 off-road UGV mobile base
- ESP32 driver board
- USB/serial communication direction from Raspberry Pi to the chassis controller

This means NeXa now has a real mobility direction.

The mobile base should be treated as a chassis subsystem, not as raw motor logic inside the assistant core.

The correct ownership boundary is:

- Raspberry Pi owns high-level movement intent
- ESP32 driver owns low-level motor/chassis control
- communication happens through a clean transport boundary
- future mobility skills should call a mobility service, not write raw serial commands directly from core assistant logic

At the current stage, mobility should still be described as:
- hardware-integrated
- manually tested / calibration-oriented
- not yet a complete autonomous navigation runtime
- not yet a closed-loop production mobility system

The next correct architecture step is to introduce or continue developing a dedicated mobility client/service boundary before exposing larger movement behaviours through normal assistant skills.

### Current battery and power hardware

The current battery-backed hardware direction includes:

- SupTronics X1206 4-cell 21700 UPS
- 21700 lithium-ion rechargeable cells, 4200mAh, 3.7V, 30A, x4
- 18650 lithium-ion rechargeable cells, 3000mAh, 3.7V, 15A
- TalentCell 12V LiFePO4 battery supply for the pan-tilt platform

The X1206 UPS is part of the main Raspberry Pi power architecture.

Its role is:
- battery-backed operation
- more embedded deployment behaviour
- safer runtime continuity than a simple temporary power cable setup
- future mobility-compatible power direction

The 21700 cells belong to the main UPS-backed Raspberry Pi power direction.

The 18650 cells belong to the wider hardware power ecosystem, especially where separate modules or external battery-powered devices require their own cells.

The TalentCell 12V LiFePO4 supply is used as the dedicated pan-tilt power direction.

This is important because the pan-tilt module should not overload or destabilise the Raspberry Pi power path.  
Keeping the pan-tilt power path separate makes the hardware setup safer and easier to reason about.

### Current embodied NeXa platform summary

The current NeXa hardware platform can now be described as:

- Raspberry Pi 5 16GB as the main runtime brain
- AI HAT+ 2 as the local AI acceleration direction
- SanDisk SSD 1TB as the main storage foundation
- 8-inch HD DSI capacitive touch display as the premium visual surface
- Raspberry Pi Camera Module 3 as the future vision input
- Waveshare 360° 2-axis pan-tilt as the physical expression and camera/display orientation layer
- 6x4 off-road UGV ESP32 driver base as the mobility foundation
- SupTronics X1206 UPS with 21700 cells as the main battery-backed compute power path
- separate TalentCell 12V LiFePO4 power for pan-tilt stability
- additional 18650 cells as part of the wider battery hardware inventory

This is a major architecture shift.

NeXa is now moving from:

- stationary voice assistant prototype

toward:

- compact local-first embodied AI assistant platform

The system should therefore continue to be developed with strict boundaries between:
- assistant logic
- visual presentation
- audio pipeline
- vision
- pan-tilt movement
- mobility
- power diagnostics
- AI workload scheduling

This is necessary to keep NeXa premium, reliable, maintainable, and safe to expand.

---

## 40. Visual Shell integration update

This section records the addition of the NeXa Visual Shell direction.

The Visual Shell is now part of the intended presentation architecture of NeXa.

It should be treated as the premium animated system face of NeXa, not as a simple screen, not as a web dashboard, and not as a temporary animation.

### Why the Visual Shell was added

NeXa needs a visual identity that matches the quality of the intended product.

A voice assistant that only speaks through a speaker and shows basic text on a small display does not match the target experience.

The Visual Shell was added to give NeXa:
- a premium animated presence
- a clear visual state model
- a system face
- stronger user feedback
- better interaction with the 8-inch DSI display
- future desktop docking behaviour
- a visual foundation for voice, vision, and system-control features

The Visual Shell exists because the display should communicate what NeXa is doing.

The user should be able to understand whether NeXa is:
- idle
- listening
- thinking
- speaking
- scanning
- showing itself
- degraded
- docked while the desktop is visible
- returning to fullscreen assistant mode

### Architectural role

The Visual Shell belongs in the presentation layer.

Its correct location is:

```text
modules/presentation/visual_shell/
```

It should not be treated as a low-level display driver.

That is important because the Visual Shell is not only responsible for drawing pixels.
It represents the assistant visually.

The correct architecture boundary is:

Python backend decides assistant state
Python backend sends visual state or visual command messages
Godot Visual Shell renders the state
Godot does not decide assistant logic
Visual Shell does not directly control Linux system actions
Visual Shell does not directly control voice, vision, mobility, or pan-tilt
Visual Shell only visualizes what the NeXa runtime tells it

This keeps the assistant architecture clean.

Current technology direction

The Visual Shell direction uses a Godot-based visual runtime.

The project should target Godot 3.6 for Raspberry Pi OS compatibility.

Godot is used because it is suitable for:

procedural animation
particle systems
smooth transitions
fullscreen visual applications
state-driven visual behaviour
future touch interaction
a more premium visual experience than a basic Python UI

The Visual Shell should be launched through:

modules/presentation/visual_shell/bin/run_visual_shell.sh

The Visual Shell should later be controlled by the Python backend through a local transport layer.

The preferred direction is:

local message protocol
local WebSocket, TCP, or IPC bridge
clear visual state contracts
health checks
safe fallback if the shell is unavailable
Current visual identity

The current target visual identity is a dark premium screen with a living particle cloud.

The default look should be:

dark background
central particle cloud
smooth breathing motion
elegant movement
subtle glow
no cheap neon overload
no visible browser interface
no unnecessary debug text
no Linux desktop panels unless desktop mode is requested

The particle cloud is the main identity of NeXa.

It should feel like a living digital presence:

calm in idle
attentive while listening
more active while thinking
pulsing while speaking
shaped into eyes when showing itself or scanning
able to shrink into a docked orb when the desktop is shown

The same particle system should transform between states instead of swapping unrelated animations.

This makes NeXa feel like one consistent entity.

Current Visual Shell behaviours

The current Visual Shell behaviour direction includes these states:

IDLE_PARTICLE_CLOUD

NeXa is present but not actively interacting.

Behaviour:

calm particle cloud
subtle breathing
low activity
central position
premium idle presence
LISTENING_CLOUD

NeXa has detected wake word or is listening.

Behaviour:

cloud becomes more attentive
slightly more open shape
controlled pulse
stronger visual focus
THINKING_SWARM

NeXa is routing, processing, using local AI, or preparing a response.

Behaviour:

cloud becomes more concentrated
particles move with controlled swarm energy
subtle processing motion
no cheap loading spinner
SPEAKING_PULSE

NeXa is speaking through TTS.

Behaviour:

particle cloud pulses while speech is active
intensity changes should feel like voice energy
first version may use simulated pulse
later version should use real audio amplitude or TTS envelope data
SCANNING_EYES

NeXa is using vision or preparing a visual inspection.

Behaviour:

cloud transforms into eyes
eyes look focused
subtle scan movement may appear
state should support future camera/vision integration
SHOW_SELF_EYES

The user asks NeXa to show itself, show eyes, or reveal its face.

Behaviour:

cloud forms calm eyes
eyes can blink
expression should be elegant, not cartoonish
NeXa can return to idle cloud after the moment ends
FACE_CONTOUR

NeXa forms a subtle abstract face from particles.

Behaviour:

minimal face outline
premium abstract shape
no realistic human face
no uncanny look
short duration unless explicitly requested
BORED_MICRO_ANIMATION

NeXa performs rare idle micro-behaviours.

Behaviour:

soft wave through particles
gentle compression/release
quick eye glimpse
rare face contour
subtle living presence

Rules:

not too frequent
not distracting
not chaotic
performance-safe
TEMPERATURE_GLYPH

NeXa shows temperature visually using particles.

Behaviour:

temperature should be formed from dense readable particles
should not rely on normal UI text as the primary expression
uses Raspberry Pi thermal data where available
useful for quick system-state presentation
BATTERY_GLYPH

NeXa shows battery visually using particles.

Behaviour:

battery level should be formed from dense readable particles
colour/state rules should match battery state
real battery data must come from a proper adapter
current generic /sys/class/power_supply/*/capacity path may not be enough for the X1206 setup

Important note:
Do not guess the X1206 battery protocol.
The final battery adapter must be implemented only after checking the real UPS documentation, I2C behaviour, sysfs exposure, CLI tools, services, or available Python packages.

DESKTOP_HIDDEN

NeXa owns the screen visually.

Behaviour:

fullscreen Visual Shell
dark background
central particle cloud
desktop hidden behind the shell
default assistant presentation mode
DESKTOP_DOCKED

The user asks to see the desktop.

Behaviour:

shell moves away from fullscreen presence
particle cloud shrinks into a docked orb
desktop becomes usable
NeXa remains present as a small assistant orb
current animation state should be preserved where possible

This is a window/layout mode, not only a particle animation state.

DESKTOP_RETURNING

The user asks NeXa to hide the desktop or return to the main assistant screen.

Behaviour:

docked orb expands
fullscreen dark interface returns
particles return to central cloud
previous assistant state can be restored cleanly
ERROR_DEGRADED

NeXa is degraded or some subsystem is unavailable.

Behaviour:

subtle error visual
amber/red accent only when needed
no aggressive flashing
should look controlled, not broken
What the Visual Shell can currently present

At the current architecture level, the Visual Shell can be used to present:

idle assistant presence
listening state
thinking state
speaking state
scanning/vision state
show-eyes / show-self state
face contour direction
desktop docked / desktop hidden behaviour
temperature glyph direction
battery glyph direction
degraded/error state

This gives NeXa a real visual language.

Instead of showing only text, NeXa can communicate state through motion, shape, density, intensity, and formation.

Voice-controlled Visual Shell commands

Visual Shell actions should be triggered by deterministic built-in command routing before the LLM.

The LLM should not be required for basic visual actions.

Important voice command groups include:

Show desktop

Examples:

pokaż pulpit
odsłoń pulpit
zdejmij shell
chcę zobaczyć pulpit
daj mi dostęp do komputera
daj mi dostęp do Linuxa
show desktop
open desktop

Expected result:

Visual Shell enters DESKTOP_DOCKED
desktop becomes usable
NeXa remains as a docked orb
Hide desktop / return to NeXa

Examples:

schowaj pulpit
wróć do siebie
wróć na ekran NeXa
zasłoń pulpit
hide desktop
return to NeXa

Expected result:

Visual Shell enters DESKTOP_RETURNING
fullscreen assistant interface returns
cloud becomes central again
Show self / show eyes

Examples:

pokaż się
pokaż oczy
spójrz na mnie
pokaż twarz
show yourself
show eyes
look at me

Expected result:

Visual Shell enters SHOW_SELF_EYES or FACE_CONTOUR
NeXa visually reveals itself through particles
Temperature

Examples:

temperatura
pokaż temperaturę
jaka jest twoja temperatura
czy jest ci za gorąco
temperature
show temperature

Expected result:

Visual Shell shows TEMPERATURE_GLYPH
NeXa may also speak the current temperature
Battery

Examples:

bateria
pokaż baterię
ile masz baterii
czy jesteś zmęczona
battery
show battery

Expected result:

Visual Shell shows BATTERY_GLYPH
NeXa may also speak the battery status
real battery value requires a real X1206 adapter later
Why deterministic routing matters

Visual Shell commands must be fast.

A command such as pokaż pulpit should not wait for a local LLM.
It should be treated as a built-in system command.

The correct flow is:

wake word
STT transcript
transcript normalization
deterministic Visual Shell command lane
visual action sent to shell
short spoken acknowledgement if appropriate
LLM prevented for this command

This protects speed and reliability.

Required Visual Shell diagnostics

The Visual Shell command path should include clear diagnostics.

For every Visual Shell voice command, the runtime should eventually be able to log:

heard_text
normalized_text
router_match
matched_rule
visual_action
transport_result
LLM_prevented
response_emitted

This is important because spoken commands may be mistranscribed.

For example:

pokaż pulpit may be heard incorrectly
spójrz na mnie may be partially recognized
short commands like bateria or temperatura may need robust matching

Diagnostics are necessary to know whether the problem is:

STT
normalization
command router
transport to Godot
Godot state handling
runtime degradation
audio feedback path
Relationship with the 8-inch DSI display

The 8-inch HD DSI capacitive touch display is now the correct primary surface for the Visual Shell.

The display gives NeXa enough space for:

full-screen particle cloud
particle eyes
face contour
readable particle glyphs
docked orb behaviour
future touch controls
future system-control confirmations
future desktop coexistence

This is why the Visual Shell should be designed around 1280x800 and performance-tested on real Raspberry Pi 5 hardware.

Relationship with pan-tilt and camera

The Visual Shell should visually support pan-tilt and camera behaviour, but not directly control them.

Example:

user says: spójrz na mnie
assistant runtime routes the command
pan-tilt service may orient the camera/display
Visual Shell shows SHOW_SELF_EYES
future vision service may confirm user presence

Another example:

user says: rozejrzyj się
assistant runtime routes the command
pan-tilt may scan
camera/vision may analyse
Visual Shell shows SCANNING_EYES

The Visual Shell should present the state.
It should not own the robotics logic.

Current implementation boundary

The current architecture rule is:

Python backend owns assistant state and command decisions
Visual Shell renders state and animation
Godot should not make assistant decisions
Python should not render particles
built-in visual commands should run before LLM
transport failures should degrade gracefully
Visual Shell must not break wake, STT, TTS, runtime, or audio output

This protects the architecture from becoming tangled.

Current value added by the Visual Shell

Adding Visual Shell gives NeXa several important improvements:

stronger premium identity
better user feedback
clearer assistant state
more natural interaction with the 8-inch display
foundation for desktop docking
foundation for visual command feedback
foundation for future touch UI
foundation for future camera-aware expression
better product feel than simple text or static eyes

The Visual Shell is therefore not cosmetic.

It is part of NeXa's product architecture.

Current limitations

The Visual Shell direction still has limitations that must be handled carefully:

performance must be tested on real Raspberry Pi 5 hardware
particle count must be tuned for smoothness
Godot version must stay compatible with Raspberry Pi OS
desktop docking depends on Linux window behaviour
transport must be robust
Visual Shell must remain optional/degradable
battery glyph needs a real X1206 data adapter later
voice-command reliability needs diagnostics and robust transcript normalization
shell startup/autostart needs systemd-level validation later
Next architecture steps

The next recommended Visual Shell steps are:

keep the Godot Visual Shell compatible with Godot 3.6
keep the shell under modules/presentation/visual_shell/
keep Python/Godot separation strict
finish deterministic Visual Shell voice command routing
add complete diagnostics for visual commands
validate shell launch with modules/presentation/visual_shell/bin/run_visual_shell.sh
verify desktop docked/hidden behaviour on the real Raspberry Pi OS desktop
keep animation smooth even if that means fewer particles
connect speaking/listening/thinking/scanning states to real runtime events
only implement real battery glyph after the X1206 battery data source is verified
Final conclusion

The Visual Shell moves NeXa from a voice assistant with a display into a visual AI presence.

It gives NeXa a system face.

The correct final direction is:

dark premium full-screen interface
living particle cloud
smooth state-driven behaviour
voice-controlled desktop docking
particle eyes and face contour
particle temperature and battery glyphs
graceful degraded state
strict backend/frontend separation
no fragile UI hacks
no LLM dependency for built-in visual commands

This is a major step toward making NeXa feel like a serious premium local-first AI assistant rather than a Raspberry Pi prototype.


## 39. NEXA Voice Engine v2 migration gate

### Status

Partially implemented.

### What changed

The project now has an explicit `voice_engine` configuration block that defines the migration gate for NEXA Voice Engine v2.

The new configuration keeps Voice Engine v2 disabled by default:

- `voice_engine.enabled=false`
- `voice_engine.mode=legacy`
- `voice_engine.realtime_audio_bus_enabled=false`
- `voice_engine.vad_endpointing_enabled=false`
- `voice_engine.command_first_enabled=false`
- `voice_engine.fallback_to_legacy_enabled=true`

This means the current wake word, audio input, FasterWhisper STT, TTS and Visual Shell runtime path remain active while the new Voice Engine v2 architecture is built safely beside the legacy path.

### Why this was needed

NEXA currently needs a major voice pipeline migration because the slow perceived response is mostly before routing:

```text
wake
→ capture
→ endpointing / waiting for speech end
→ STT
→ routing

```

## 40. NEXA Voice Engine v2 — RealtimeAudioBus foundation

### Status

Partially implemented.

### What changed

The project now has the first foundation layer for NEXA Voice Engine v2: a realtime audio bus.

New modules were added under:

```text
modules/devices/audio/realtime/
```

### The foundation includes:

AudioFrame — immutable PCM frame contract,
AudioRingBuffer — thread-safe duration-limited audio frame buffer,
AudioBus — central realtime audio publisher/subscriber bus,
AudioBusSubscription — independent read cursor for consumers such as VAD, command ASR and fallback STT,
AudioDeviceConfig — canonical realtime audio capture settings,
AudioCaptureWorker — source-injected capture worker that can publish PCM frames to the bus.

The capture worker is intentionally source-injected and not connected to sounddevice, PyAudio, FasterWhisper or the current wake runtime yet.

### Why this was needed

The current voice pipeline still depends too much on the legacy capture/STT path before built-in commands can be routed.

### The long perceived delay is mainly before routing:

wake
→ capture
→ endpointing / waiting for speech end
→ STT
→ routing

Voice Engine v2 needs a central realtime audio foundation so that wake word, VAD endpointing, command-first recognition and fallback STT can consume the same audio stream without each subsystem owning its own incompatible capture logic.

### What NEXA gains

NEXA gains:

a clean audio foundation for Voice Engine v2,
independent audio consumers through subscriptions,
safer future integration of VAD and command ASR,
no runtime disruption because the new bus is not connected to the production voice path yet,
better maintainability by separating realtime audio transport from STT backend logic.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper, TTS and Visual Shell paths remain active.

### Temporary legacy retention rule:

FasterWhisper capture remains the production path until Voice Engine v2 integration passes runtime acceptance tests,
the realtime bus remains isolated behind the Voice Engine v2 migration plan,
duplicated audio buffering helpers should be reviewed after VAD endpointing and command ASR are integrated.
Source / evidence

### This decision is based on:

local NEXA runtime observations showing delay before routing,
NEXA Voice Engine v2 execution rules,
current project architecture where Visual Shell command dispatch is already fast but capture/STT path is still slow,
the need to avoid breaking wake word, audio input, TTS and Visual Shell during migration.


## 41. NEXA Voice Engine v2 — VAD endpointing foundation

### Status

Partially implemented.

### What changed

The project now has a first-class VAD endpointing foundation for NEXA Voice Engine v2.

New modules were added under:

```text
modules/devices/audio/vad/
```

The foundation includes:

VadDecision — frame-level speech/silence decision,
VadEvent — endpointing event emitted from VAD decisions,
VadEventType — stable event type enum for speech start, continuation, end and silence,
VadEngine — protocol for VAD engines,
SileroVadEngine — Silero-compatible adapter with injected score provider,
EndpointingPolicy — stateful policy that turns frame-level VAD decisions into speech start/end events,
EndpointingPolicyConfig — timing configuration for minimum speech and silence durations.

The Silero adapter intentionally does not load a real model yet. It uses an injected score provider so the contract can be tested without changing the current production wake/STT runtime.

### Why this was needed

NEXA Voice Engine v2 needs to detect speech start and speech end quickly and consistently.

The current perceived delay is mostly before command routing:

wake
→ capture
→ endpointing / waiting for speech end
→ STT
→ routing

The existing runtime still depends on the legacy capture/STT path, where endpointing behaviour is tied to capture timing and FasterWhisper flow. Voice Engine v2 needs endpointing as a separate architectural component so built-in commands can later be recognized before full STT/LLM fallback.

### What NEXA gains

NEXA gains:

a dedicated VAD endpointing layer,
a clean contract between realtime audio frames and speech boundary events,
lower-risk future integration of command-first recognition,
testable speech start/end timing rules,
no disruption to the current wake word, FasterWhisper, TTS or Visual Shell runtime.
Removed or deprecated legacy path

### No legacy runtime path was removed in this stage.

The existing FasterWhisper capture and endpointing logic remains active for production runtime until Voice Engine v2 integration passes runtime acceptance tests.

### Temporary legacy retention rule:

old capture timing remains only for legacy runtime mode,
new VAD endpointing remains isolated until Voice Engine v2 is enabled,
duplicated endpointing constants should be reviewed after the new pipeline starts consuming realtime audio frames.
Source / evidence

### This decision is based on:

NEXA Voice Engine v2 execution rules,
local NEXA runtime observations showing delay before routing,
Stage 1 realtime audio bus foundation,
the requirement that built-in commands must eventually execute before full STT/LLM fallback.


## 42. NEXA Voice Engine v2 — bilingual command recognizer grammar

### Status

Partially implemented.

### What changed

The project now has the first command-first recognition foundation for NEXA Voice Engine v2.

New modules were added under:

```text
modules/devices/audio/command_asr/
```

The foundation includes:

CommandLanguage — command language enum for Polish, English and unknown,
detect_command_language() — lightweight language detection for short built-in command utterances,
CommandPhrase — phrase-to-intent grammar entry,
CommandRecognitionResult — stable result contract for command-first recognition,
CommandRecognitionStatus — matched, no-match and ambiguous states,
CommandGrammar — deterministic bilingual phrase matcher,
GrammarCommandRecognizer — text-only recognizer backed by the command grammar,
VoskCommandRecognizer — Vosk-compatible recognizer shell with injected PCM transcript provider,
build_default_command_grammar() — first canonical bilingual grammar for built-in commands.

The initial grammar covers key Polish and English command families:

Visual Shell desktop access,
returning to the assistant shell,
battery state,
temperature state,
current time,
current date,
assistant help,
assistant identity,
focus mode start/stop.

The grammar also includes explicit STT recovery variants for common misrecognitions such as pulpid / pulbit, so commands like pokaż pulpit can be handled more reliably later without adding more patches inside the Visual Shell router.

Why this was needed

NEXA currently depends too much on full STT output and downstream routing for clear built-in commands.

Voice Engine v2 requires a command-first recognizer so short deterministic commands can be recognized before full LLM or conversation fallback.

This stage creates the command grammar as a future canonical source of command phrases, instead of continuing to duplicate phrase lists across Visual Shell routing, session routing and fallback parsing.

What NEXA gains

NEXA gains:

a bilingual command-first recognition contract,
a cleaner place to add Polish and English built-in command variants,
deterministic matching for clear system commands,
explicit no-match behaviour for open questions that should go to STT/LLM fallback,
a safer migration path toward fast built-in command execution,
less pressure to keep patching Visual Shell router phrase lists.
Removed or deprecated legacy path

No runtime path was removed in this stage.

The existing Visual Shell command router phrase matching remains active only because Voice Engine v2 is not yet integrated into production runtime.

Temporary legacy retention rule:

old Visual Shell command phrase lists stay until CommandIntentResolver integration,
new command phrase variants should be added to modules/devices/audio/command_asr/command_grammar.py,
duplicated command phrase ownership must be removed when Voice Engine v2 becomes the primary command path.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
local runtime observations showing that built-in commands still depend on the slower capture/STT path,
Stage 1 realtime audio bus foundation,
Stage 2 VAD endpointing foundation,
the product requirement that Polish and English commands must both be understood naturally per turn.


## 43. NEXA Voice Engine v2 — CommandIntentResolver foundation

### Status

Partially implemented.

### What changed

The project now has a deterministic command intent resolution layer for NEXA Voice Engine v2.

New modules were added under:

```text
modules/core/command_intents/
```

The foundation includes:

CommandIntentDomain — high-level command domains such as Visual Shell, system, assistant and focus,
CommandIntentDefinition — static mapping between an intent key and executable action,
CommandIntent — resolved deterministic intent with language, action, confidence and source text,
CommandIntentResolutionResult — stable resolver output contract,
CommandIntentResolutionStatus — resolved, no-intent, low-confidence, ambiguous and unknown-intent states,
ConfidencePolicy — acceptance/rejection policy for command recognition confidence,
visual_shell_intents.py — Visual Shell intent definitions,
system_intents.py — system, assistant and focus intent definitions,
CommandIntentResolver — resolver that converts command recognizer output into deterministic command intents.
Why this was needed

NEXA Voice Engine v2 must separate recognition, intent resolution and execution.

Before this stage, command recognition could identify a phrase and produce an intent key, but there was no stable architectural layer responsible for deciding whether a recognition result should become an executable command.

This stage creates that separation:

CommandRecognizer
→ CommandIntentResolver
→ execution layer later

This prevents the project from continuing to push recognition, confidence decisions and execution routing into one router.

What NEXA gains

NEXA gains:

deterministic intent resolution for built-in commands,
clearer separation between command recognition and command execution,
explicit confidence rejection instead of unsafe fuzzy execution,
language-aware command intents,
a cleaner path to visual-action-first execution,
reduced risk of sending clear built-in commands to the LLM.
Removed or deprecated legacy path

No runtime path was removed in this stage.

The existing Visual Shell router and legacy command matching remain active only because Voice Engine v2 is not integrated into runtime yet.

Temporary legacy retention rule:

legacy Visual Shell phrase matching stays until Voice Engine v2 command path is integrated,
new phrase recognition belongs in modules/devices/audio/command_asr/command_grammar.py,
new intent routing belongs in modules/core/command_intents/,
duplicated phrase ownership should be removed after runtime integration passes acceptance tests.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 1 realtime audio bus foundation,
Stage 2 VAD endpointing foundation,
Stage 3 bilingual command recognizer grammar,
the product requirement that built-in commands must be deterministic and execute before LLM fallback.


## 44. NEXA Voice Engine v2 — command-first pipeline contract

### Status

Partially implemented.

### What changed

The project now has the first top-level Voice Engine v2 command-first pipeline contract.

New modules were added under:

```text
modules/core/voice_engine/
```

The foundation includes:

VoiceTurnState — lifecycle state enum for one voice turn,
VoiceTurnRoute — final route enum for command, fallback or rejection,
VoiceTurnInput — stable input contract for one Voice Engine v2 turn,
VoiceTurnResult — stable output contract for command or fallback routing,
VoiceEngineMetrics — per-turn timing and fallback metrics,
VoiceEngineSettings — typed feature-gate settings for Voice Engine v2,
VoiceLanguagePolicy — per-turn language selection policy,
FallbackDecision and FallbackPipeline — explicit fallback contract,
CommandFirstPipeline — pipeline that runs command recognition before fallback,
VoiceEngine — top-level facade that respects the voice_engine migration gate.

The new pipeline combines:

CommandRecognizer
→ CommandIntentResolver
→ command result or fallback decision

The production runtime is not changed in this stage.

Why this was needed

NEXA Voice Engine v2 needs a clean command-first pipeline before runtime integration.

Earlier stages added separate foundations:

Stage 1: RealtimeAudioBus
Stage 2: VAD endpointing
Stage 3: bilingual command grammar
Stage 4: CommandIntentResolver

This stage creates the first top-level pipeline contract that can coordinate recognition, intent resolution, language policy, fallback decisions and metrics.

This avoids turning the existing runtime loop or Visual Shell router into a larger monolithic command system.

What NEXA gains

NEXA gains:

a command-first pipeline that can resolve clear built-in commands before fallback,
explicit fallback reasons for non-command turns,
per-turn metrics such as command recognition time and intent resolution time,
a typed settings layer that prevents accidental runtime replacement,
a safer path toward future runtime integration,
stronger separation between recognition, intent resolution, fallback and execution.
Removed or deprecated legacy path

No production runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains active while voice_engine.enabled=false,
Voice Engine v2 command-first pipeline remains isolated until runtime integration tests pass,
old Visual Shell phrase matching should be deprecated only after the command-first pipeline becomes the primary command path.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 1 realtime audio bus foundation,
Stage 2 VAD endpointing foundation,
Stage 3 bilingual command recognizer grammar,
Stage 4 deterministic command intent resolver,
local runtime evidence that the latency bottleneck is before routing, not inside Visual Shell command dispatch.


## 45. NEXA Voice Engine v2 — safe runtime integration adapter

### Status

Partially implemented.

### What changed

The project now has a safe runtime integration adapter for NEXA Voice Engine v2.

New modules were added under:

```text
modules/runtime/voice_engine_v2/
```

The adapter can build an isolated Voice Engine v2 runtime bundle from existing project settings:

VoiceEngineV2RuntimeBundle — isolated runtime bundle containing the engine, typed settings and status,
build_voice_engine_v2_runtime() — factory that constructs the command-first pipeline from settings,
RuntimeBuilderVoiceEngineV2Mixin — builder mixin that creates the Voice Engine v2 bundle,
RuntimeBuilder metadata integration — exposes Voice Engine v2 in runtime.metadata.

The production runtime path is not replaced in this stage.

Voice Engine v2 is exposed only through metadata keys:

voice_engine_v2
voice_engine_v2_settings
voice_engine_v2_status
voice_engine_v2_metadata

It is intentionally not added to backend_statuses yet, so it does not affect startup readiness, product readiness or premium readiness.

Why this was needed

Earlier stages created the internal Voice Engine v2 foundations:

Stage 1: RealtimeAudioBus
Stage 2: VAD endpointing
Stage 3: bilingual command recognizer grammar
Stage 4: CommandIntentResolver
Stage 5: command-first pipeline contract

This stage gives the runtime builder a safe way to construct Voice Engine v2 without switching production traffic to it.

This is required before any real runtime integration because NEXA must not break:

wake word,
audio input,
FasterWhisper STT,
TTS,
Visual Shell command execution.
What NEXA gains

NEXA gains:

a safe runtime-visible Voice Engine v2 adapter,
typed Voice Engine v2 settings built from existing config,
clear metadata showing whether the new command pipeline can run,
no impact on current production voice behaviour,
a controlled bridge toward future runtime integration.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary while voice_engine.enabled=false,
Voice Engine v2 is visible in metadata only,
Voice Engine v2 must not be added to startup/premium readiness gates until runtime acceptance tests are created,
old Visual Shell phrase matching remains until command-first execution integration is validated.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
current config keeping voice_engine.enabled=false,
Stage 1 realtime audio bus foundation,
Stage 2 VAD endpointing foundation,
Stage 3 bilingual command recognizer grammar,
Stage 4 deterministic command intent resolver,
Stage 5 command-first pipeline contract,
the requirement to avoid breaking current wake/STT/TTS/Visual Shell runtime.


## 46. NEXA Voice Engine v2 — visual-action-first execution adapter

### Status

Partially implemented.

### What changed

The project now has a visual-action-first execution adapter for NEXA Voice Engine v2.

New modules were added under:

```text
modules/core/voice_engine/execution/
```

The execution layer includes:

IntentExecutionRequest — execution request for a resolved command intent,
IntentExecutionResult — execution result with action-first and TTS-order metadata,
IntentExecutionStatus — executed, no-handler, failed and rejected states,
IntentExecutionAdapter — registry-based executor for resolved intent actions,
VisualActionFirstExecutor — executor that runs deterministic command actions before optional spoken acknowledgement,
visual_shell_actions.py — Visual Shell action classification for commands that should not wait for TTS acknowledgement.

The new executor enforces the product rule:

resolved command intent
→ execute action first
→ optional spoken acknowledgement later

For Visual Shell commands such as show_desktop and show_shell, spoken acknowledgement is disabled by default at this layer because the visual state change itself is the immediate feedback.

Why this was needed

NEXA must feel fast and premium.

For built-in visual commands, the user should not wait for Piper/TTS before seeing the desktop, shell, eyes or other Visual Shell state changes.

The previous architecture could still allow spoken confirmation or downstream response delivery to influence perceived action timing. Voice Engine v2 needs a dedicated execution contract where deterministic actions are executed first, and spoken acknowledgement is optional and secondary.

What NEXA gains

NEXA gains:

an action-first execution contract for resolved Voice Engine v2 intents,
a clear place to connect future Visual Shell execution handlers,
explicit metadata showing whether an action executed before TTS,
no dependency on TTS for fast visual commands,
safer future runtime integration because execution handlers are injected and testable,
cleaner separation between command recognition, intent resolution and execution.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing Visual Shell router and visual_shell_command_lane.py remain active because Voice Engine v2 is still not the primary production command path.

Temporary legacy retention rule:

legacy Visual Shell execution remains until Voice Engine v2 execution integration is validated,
new Voice Engine v2 command execution should use modules/core/voice_engine/execution/,
visual commands must execute before optional TTS acknowledgement,
duplicated Visual Shell phrase matching should be removed only after runtime acceptance tests pass.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 5 command-first pipeline contract,
current config keeping voice_engine.enabled=false,
product requirement that built-in commands respond within 2 seconds, with premium target 300–900 ms,
observed runtime problem where long silence and pre-routing delays hurt perceived responsiveness.


## 47. NEXA Voice Engine v2 — command latency benchmark gates

### Status

Partially implemented.

### What changed

The project now has benchmark gates for NEXA Voice Engine v2 command-first responsiveness.

New benchmark modules were added under:

```text
benchmarks/voice/
```

The benchmark layer includes:

benchmark_command_latency.py — deterministic command-first latency benchmark,
benchmark_endpointing_latency.py — deterministic VAD endpointing latency benchmark,
benchmark_full_voice_turn.py — combined command + endpointing benchmark gate.

The command benchmark measures:

speech_end_to_action_ms,
command_recognition_ms,
intent_resolution_ms,
command success rate,
fallback usage for built-in commands.

The endpointing benchmark measures:

speech start detection delay,
speech end / endpoint delay.

The combined benchmark provides one high-level acceptance result for Voice Engine v2 command turns.

Why this was needed

NEXA Voice Engine v2 is performance-driven. The product target is not only architectural cleanliness; built-in commands must feel fast.

The project target is:

Built-in commands:
- required: <= 2 seconds from speech end to action
- premium target: 300–900 ms from speech end to action

Without benchmark gates, Voice Engine v2 could accidentally drift back toward slow behaviour where clear built-in commands wait for full STT, routing or LLM fallback.

This stage makes command speed measurable before production runtime integration.

What NEXA gains

NEXA gains:

measurable command-first responsiveness,
explicit acceptance gates for built-in commands,
detection of accidental fallback usage for clear commands,
benchmark evidence before enabling Voice Engine v2 in runtime,
a safer route toward premium latency targets,
a repeatable validation tool for future changes.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary while voice_engine.enabled=false,
benchmark gates validate Voice Engine v2 before runtime replacement,
old Visual Shell phrase matching should only be removed after Voice Engine v2 command execution passes runtime acceptance tests.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 1 realtime audio bus foundation,
Stage 2 VAD endpointing foundation,
Stage 3 bilingual command recognizer grammar,
Stage 4 deterministic command intent resolver,
Stage 5 command-first pipeline contract,
Stage 6 safe runtime integration adapter,
Stage 7 visual-action-first execution adapter,
local runtime observations showing that perceived delay happens before routing.


## 48. NEXA Voice Engine v2 — runtime acceptance adapter for command-first execution

### Status

Partially implemented.

### What changed

The project now has a guarded runtime acceptance adapter for NEXA Voice Engine v2 command-first execution.

New runtime acceptance code was added under:

```text
modules/runtime/voice_engine_v2/
```

The acceptance layer includes:

VoiceEngineV2AcceptanceRequest — controlled request for testing Voice Engine v2 command-first execution,
VoiceEngineV2AcceptanceResult — acceptance result with command, fallback and execution metadata,
VoiceEngineV2AcceptanceAdapter — guarded adapter that runs command-first processing and action-first execution only when the Voice Engine v2 settings gate allows it,
VoiceEngineV2RuntimeBundle.acceptance_adapter — runtime-visible adapter attached to the isolated Voice Engine v2 bundle,
runtime metadata key voice_engine_v2_acceptance_adapter.

The adapter can execute a transcript through:

VoiceEngine v2
→ command-first pipeline
→ intent resolution
→ visual-action-first execution adapter

It refuses to run when voice_engine.command_pipeline_can_run is false. This keeps the legacy production runtime primary while allowing controlled acceptance tests.

Why this was needed

Previous stages built Voice Engine v2 foundations but did not provide a safe runtime-facing way to validate the full command-first path.

This stage adds a guarded acceptance adapter so command-first execution can be tested end-to-end without replacing the production wake/capture/STT runtime.

NEXA needs this intermediate layer because the next risky step is runtime integration. Before that, the system must prove that Voice Engine v2 can:

resolve a built-in command,
avoid fallback for clear built-ins,
execute the mapped action before TTS,
reject or fallback safely for non-command text,
stay disabled when config requires legacy mode.
What NEXA gains

NEXA gains:

a controlled runtime acceptance path for Voice Engine v2,
end-to-end command-first validation without production takeover,
explicit disabled-mode behaviour,
safe testing of action-first execution handlers,
clearer separation between acceptance testing and live runtime switching,
a better bridge toward hardware validation on Raspberry Pi.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary while voice_engine.enabled=false,
Voice Engine v2 acceptance adapter is exposed in metadata only,
Voice Engine v2 must not replace the main loop until hardware runtime validation confirms wake word, audio input, TTS and Visual Shell stability,
old Visual Shell command phrase matching remains until the command-first path is accepted on real hardware.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 5 command-first pipeline contract,
Stage 6 safe runtime integration adapter,
Stage 7 visual-action-first execution adapter,
Stage 8 command latency benchmark gates,
current benchmark results showing command_success_rate=1.0, fallback_count=0, p95_speech_end_to_action_ms=50.0 and endpoint_delay_ms=260.0 in deterministic tests.


## 49. NEXA Voice Engine v2 — hardware-safe shadow mode

### Status

Partially implemented.

### What changed

The project now has hardware-safe shadow mode for NEXA Voice Engine v2.

Shadow mode lets the runtime observe transcripts and compare Voice Engine v2 decisions against the legacy runtime decision without executing any action.

New runtime module:

```text
modules/runtime/voice_engine_v2/shadow_mode.py
```
The shadow mode layer includes:

VoiceEngineV2ShadowRequest — transcript observation request,
VoiceEngineV2ShadowResult — comparison result between legacy routing and Voice Engine v2,
VoiceEngineV2ShadowModeAdapter — safe observer that runs Voice Engine v2 decision logic without executing actions.

New configuration keys:

voice_engine.shadow_mode_enabled=false
voice_engine.shadow_log_path="var/data/voice_engine_v2_shadow.jsonl"

The adapter is also exposed through runtime metadata as:

voice_engine_v2_shadow_mode_adapter
Why this was needed

The next risky step is real runtime integration.

Before replacing any part of the production wake/capture/STT path, NEXA needs a safe way to compare what legacy routing does versus what Voice Engine v2 would do.

Shadow mode allows this without:

executing actions,
changing Visual Shell state,
using TTS,
changing wake word,
replacing FasterWhisper capture/STT,
affecting production runtime readiness.
What NEXA gains

NEXA gains:

hardware-safe validation before runtime takeover,
a way to detect mismatches between legacy routing and Voice Engine v2,
a safe path for Raspberry Pi testing,
no accidental action execution during shadow checks,
clearer evidence for when legacy phrase matching can later be removed,
stronger confidence before enabling command-first runtime execution.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary,
shadow mode only observes,
shadow mode never executes actions,
old Visual Shell phrase matching remains until real hardware shadow-mode validation proves Voice Engine v2 decisions are correct.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 8 benchmark results showing command_success_rate=1.0, fallback_count=0, p95_speech_end_to_action_ms=50.0 and endpoint_delay_ms=260.0,
the need to avoid breaking wake word, audio input, TTS and Visual Shell,
the product requirement that built-in commands must be deterministic before LLM fallback.


## 50. NEXA Voice Engine v2 — shadow-mode telemetry persistence

### Status

Partially implemented.

### What changed

The project now persists Voice Engine v2 shadow-mode observations to JSONL.

New module:

```text
modules/runtime/voice_engine_v2/shadow_telemetry.py
```
The telemetry layer includes:

VoiceEngineV2ShadowTelemetryRecord — serializable shadow-mode observation record,
VoiceEngineV2ShadowTelemetryWriter — append-only JSONL writer,
integration with VoiceEngineV2ShadowModeAdapter.

Shadow-mode records are written to:

var/data/voice_engine_v2_shadow.jsonl

or to the configured value of:

voice_engine.shadow_log_path

Each record includes:

turn ID,
transcript,
legacy route,
legacy intent key,
Voice Engine v2 route,
Voice Engine v2 intent key,
Voice Engine v2 language,
fallback reason,
match/mismatch status against legacy intent,
action execution flag,
command recognition timing,
intent resolution timing,
speech-end-to-finish timing.

Shadow mode still never executes actions.

Why this was needed

Shadow mode is useful only if it creates evidence.

Before enabling Voice Engine v2 in production runtime, NEXA needs hardware-safe telemetry showing how Voice Engine v2 decisions compare against legacy runtime decisions on the Raspberry Pi.

The telemetry file makes it possible to review real spoken-command behaviour without changing the live wake/capture/STT/TTS path.

What NEXA gains

NEXA gains:

persistent hardware validation evidence,
JSONL logs for comparing legacy routing with Voice Engine v2,
safer decision-making before runtime takeover,
proof that shadow mode does not execute actions,
measurable timing data for command-first processing,
a cleanup path for later removing duplicated legacy phrase matching.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary,
shadow mode only observes and logs,
telemetry is written only for enabled shadow-mode observations,
legacy Visual Shell phrase matching remains until hardware shadow telemetry proves Voice Engine v2 is stable and correct.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 10 hardware-safe shadow mode,
benchmark results showing command_success_rate=1.0, fallback_count=0, p95_speech_end_to_action_ms=50.0 and endpoint_delay_ms=260.0,
the need to collect Raspberry Pi runtime evidence before replacing the legacy voice path.


## 51. NEXA Voice Engine v2 — hardware shadow-mode runtime hook

### Status

Partially implemented.

### What changed

The project now has a hardware-safe runtime hook for feeding legacy runtime transcripts into Voice Engine v2 shadow mode.

New module:

```text
modules/runtime/voice_engine_v2/shadow_runtime_hook.py
```
The hook layer includes:

VoiceEngineV2ShadowRuntimeObservation — passive observation object for a legacy voice turn,
VoiceEngineV2ShadowRuntimeHook — passive runtime hook that forwards transcripts to shadow mode,
VoiceEngineV2RuntimeBundle.shadow_runtime_hook — runtime-visible hook attached to the Voice Engine v2 bundle,
runtime metadata key voice_engine_v2_shadow_runtime_hook.

The hook can observe:

legacy transcript
→ legacy route
→ legacy intent key
→ Voice Engine v2 shadow decision
→ JSONL telemetry

It never executes actions.

Why this was needed

Stage 11 added persistent shadow-mode telemetry, but the runtime still needed a safe hook object that can later be called from the legacy voice path after transcript routing.

This hook creates that bridge without changing production behaviour.

It is safe for Raspberry Pi validation because it does not:

execute Visual Shell actions,
trigger TTS,
change wake word,
replace FasterWhisper capture/STT,
change legacy routing,
affect runtime readiness.
What NEXA gains

NEXA gains:

a safe runtime-facing shadow-mode observation hook,
a clear bridge between legacy transcripts and Voice Engine v2 decision comparison,
persistent telemetry from real runtime turns once connected,
no action execution during shadow validation,
a better evidence path before enabling command-first execution,
a future cleanup path for duplicated Visual Shell phrase matching.
Removed or deprecated legacy path

No legacy runtime path was removed in this stage.

The existing wake word, FasterWhisper capture/STT, TTS and Visual Shell runtime remain active.

Temporary legacy retention rule:

legacy runtime remains primary,
shadow runtime hook only observes,
hook returns None for empty transcripts,
hook never executes actions,
legacy Visual Shell phrase matching remains until hardware shadow telemetry proves Voice Engine v2 correctness.
Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 10 hardware-safe shadow mode,
Stage 11 shadow-mode telemetry persistence,
benchmark evidence showing command_success_rate=1.0, fallback_count=0, p95_speech_end_to_action_ms=50.0 and endpoint_delay_ms=260.0,
the requirement to avoid breaking current wake/STT/TTS/Visual Shell runtime.


## 52. NEXA Voice Engine v2 — guarded legacy transcript tap

### Status

Partially implemented.

### What changed

Stage 13 adds a guarded transcript observation tap from the legacy runtime into Voice Engine v2 shadow mode.

The tap is placed in:

```text
modules/core/assistant_impl/interaction_mixin.py
```

The hook is called only after the legacy live path has already executed.

Correct flow:

legacy transcript
→ legacy route decision
→ legacy live execution
→ Voice Engine v2 shadow observation
→ return original legacy result

The tap handles both legacy execution branches:

fast lane path
normal RouteDecision path

The hook forwards only lightweight metadata:

turn id,
transcript,
legacy route,
legacy primary intent,
language hint,
started monotonic timestamp,
speech-end monotonic timestamp when available,
handled flag,
route path,
dispatch latency,
route confidence,
input source,
capture phase.

It does not pass runtime objects, backend objects, audio bytes, capture buffers, Visual Shell objects, or large payloads.

Why this was needed

Stages 10–12 created hardware-safe shadow mode, JSONL telemetry, and the runtime hook object, but the real legacy runtime still did not feed accepted transcripts into the shadow path.

Stage 13 connects the legacy runtime to shadow telemetry without making Voice Engine v2 production-primary.

The hook is intentionally placed after live execution so Voice Engine v2 shadow mode cannot delay or block the live action.

What NEXA gains

NEXA gains real transcript evidence from the current production legacy path while preserving runtime safety.

This enables comparison between:

legacy route kind,
legacy primary intent,
Voice Engine v2 command-first route,
Voice Engine v2 intent,
fallback reason,
language detection.

This gives data needed before any future takeover decision.

Runtime safety is preserved:

wake word is unchanged,
audio input is unchanged,
FasterWhisper is unchanged,
TTS is unchanged,
Visual Shell live state is still controlled only by legacy runtime,
Voice Engine v2 does not execute actions,
Voice Engine v2 does not trigger TTS,
Voice Engine v2 does not replace the live route.
Removed or deprecated legacy path

No legacy runtime code was removed.

These files remain untouched as production-primary paths:

modules/runtime/main_loop/*
modules/devices/audio/input/faster_whisper/*
modules/presentation/visual_shell/controller/voice_command_router.py
modules/core/session/visual_shell_command_lane.py

Cleanup performed:

removed unused VOICE_STATE_ROUTING import from modules/core/assistant_impl/interaction_mixin.py,
removed duplicated shadow_mode_enabled and shadow_mode_can_run metadata keys from modules/runtime/voice_engine_v2/factory.py.

Planned removal point:

Legacy command recognition and duplicated Visual Shell phrase handling can only be removed after hardware shadow telemetry proves that Voice Engine v2 matches or improves legacy behaviour across real bilingual turns.

Source / evidence

This decision is based on:

NEXA Voice Engine v2 execution rules,
Stage 10 hardware-safe shadow mode,
Stage 11 shadow telemetry persistence,
Stage 12 shadow runtime hook,
current benchmark acceptance:
command_success_rate=1.0,
fallback_count=0,
p50_speech_end_to_action_ms=50.0,
p95_speech_end_to_action_ms=50.0,
endpoint_delay_ms=260.0,
source audit showing that CoreAssistantInteractionMixin.handle_command() has the safest post-route and post-execution observation point.


## 53. NEXA Voice Engine v2 — shadow telemetry validator

### Status

Implemented.

### What changed

Stage 14 adds an offline validator for Voice Engine v2 shadow-mode telemetry.

New files:

```text
scripts/validate_voice_engine_v2_shadow_log.py
tests/scripts/test_validate_voice_engine_v2_shadow_log.py
```

The validator reads:

var/data/voice_engine_v2_shadow.jsonl

It validates that shadow-mode telemetry remains safe before any future production takeover decision.

The validator checks:

valid JSONL format,
no Voice Engine v2 action execution,
legacy_runtime_primary=true,
non-empty transcript,
present legacy route,
present legacy intent,
present Voice Engine v2 intent,
intent mismatch count,
route mismatch count,
fallback count.
Why this was needed

Stage 13 connected the legacy runtime to Voice Engine v2 shadow observation.

Before enabling shadow mode on real hardware for longer validation, NEXA needs a lightweight way to inspect the collected data and prove that shadow mode is still only observing.

This stage intentionally does not add anything to the runtime hot path.

What NEXA gains

NEXA gains a safe validation step for real transcript telemetry.

This helps confirm:

Voice Engine v2 does not execute actions in shadow mode,
legacy runtime remains the only live execution path,
command-first intent matching can be compared against legacy behaviour,
mismatches are visible before any migration decision,
telemetry quality can be checked without slowing down wake/capture/STT/TTS.
Removed or deprecated legacy path

No legacy runtime path was removed.

No production runtime path was changed.

This stage adds only offline validation tooling.

Source / evidence

This decision is based on:

Stage 13 guarded legacy transcript tap,
Voice Engine v2 shadow-mode JSONL telemetry,
NEXA Voice Engine v2 requirement that architecture decisions must be backed by local runtime logs, benchmarks and tests,
runtime-safety requirement that Voice Engine v2 must not execute actions while still in shadow mode.


## 54. NEXA Voice Engine v2 — shadow telemetry inspector

### Status

Implemented.

### What changed

Stage 15 adds an offline inspection/report script for Voice Engine v2 shadow-mode telemetry.

New files:

```text
scripts/inspect_voice_engine_v2_shadow_log.py
tests/scripts/test_inspect_voice_engine_v2_shadow_log.py
```

The script reads:

var/data/voice_engine_v2_shadow.jsonl

It produces a human-readable report with:

total record count,
JSON load issue count,
action-executed count,
non-legacy-primary count,
empty transcript count,
intent mismatch count,
route mismatch count,
fallback count,
language distribution,
route path distribution,
top legacy intents,
top Voice Engine v2 intents,
fallback reasons,
latency summaries when present,
sample records for mismatches and safety failures.
Why this was needed

Stage 14 validates whether shadow telemetry is safe.

Stage 15 explains what the telemetry actually contains.

This is needed before any production takeover decision because NEXA must not switch to Voice Engine v2 based only on synthetic tests. The system needs real transcript evidence from hardware shadow-mode runs.

What NEXA gains

NEXA gains a practical analysis tool for real hardware validation.

The inspector helps answer:

which built-in commands are already matching,
which commands mismatch,
whether fallback is being used too often,
whether Polish and English inputs are both represented,
whether shadow mode is still action-safe,
whether latency metadata shows any problem.

This supports the product goal of keeping NEXA fast, natural, measurable and local-first without slowing the runtime path.

Removed or deprecated legacy path

No legacy runtime path was removed.

No production runtime path was changed.

This stage adds only offline inspection tooling.

Source / evidence

This decision is based on:

Stage 13 guarded legacy transcript tap,
Stage 14 shadow telemetry validator,
NEXA Voice Engine v2 requirement that runtime migration must be evidence-based,
current benchmark acceptance for command-first path,
requirement that Voice Engine v2 shadow mode must not execute actions or change the live route.


# NEXA Voice Engine v2 — controlled hardware shadow validation runbook

## Purpose

This runbook describes how to run a controlled hardware validation pass for NEXA Voice Engine v2 shadow mode.

The goal is to collect real legacy transcripts and compare them with Voice Engine v2 command-first intent resolution without making Voice Engine v2 production-primary.

Correct runtime rule:

```text
legacy transcript
→ legacy route decision
→ legacy live execution
→ Voice Engine v2 shadow observation
→ return original legacy result

Voice Engine v2 shadow mode must not:

execute actions,
trigger TTS,
change Visual Shell state,
replace wake/capture/STT,
change the live route,
delay live execution.
Safety requirements

Before enabling shadow mode, the config must remain:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true

Only this flag is allowed to change during the run:

voice_engine.shadow_mode_enabled=true

After validation, it must be restored to:

voice_engine.shadow_mode_enabled=false
Pre-flight

Run from the repository root:

cd ~/Projects/smart-desk-ai-assistant
source .venv/bin/activate

Check current status:

python scripts/set_voice_engine_v2_shadow_mode.py --status

Expected safe status:

safe_to_enable_shadow: True
voice_engine.enabled: False
voice_engine.mode: legacy
voice_engine.command_first_enabled: False
voice_engine.shadow_mode_enabled: False

Run the offline tooling before the hardware run:

python scripts/validate_voice_engine_v2_shadow_log.py --allow-missing
python scripts/inspect_voice_engine_v2_shadow_log.py --allow-missing
Enable shadow mode

Enable shadow mode and archive any old telemetry log:

python scripts/set_voice_engine_v2_shadow_mode.py --enable --archive-existing-log

Check status again:

python scripts/set_voice_engine_v2_shadow_mode.py --status

Expected:

voice_engine.shadow_mode_enabled: True
safe_to_enable_shadow: True
Run NEXA

Start NEXA exactly the same way as in normal runtime testing.

Do not change wake word, audio input, FasterWhisper, TTS, Visual Shell or runtime launch mode for this validation.

The only intended difference is:

voice_engine.shadow_mode_enabled=true
Fixed command set

Speak each command naturally after the wake word.

English commands:

show desktop
show shell
what time is it
what is today's date
help
what is your name
battery
temperature
start focus mode for five minutes
stop focus mode

Polish commands:

pokaż pulpit
pokaż shell
która godzina
jaka jest dzisiaj data
pomoc
jak się nazywasz
bateria
temperatura
włącz tryb skupienia na pięć minut
zatrzymaj tryb skupienia

STT recovery variants to try once if time allows:

pulpit
pulpid
pulbit
pokaż pulpid
pokaż pulbit
Runtime expectations

During the run:

live actions must still happen through legacy runtime,
Visual Shell state must still be changed only by legacy runtime,
Voice Engine v2 must not speak,
Voice Engine v2 must not execute actions,
NEXA should feel as fast as before,
no additional dead silence should appear.

If NEXA becomes noticeably slower, stop the run and disable shadow mode.


## 55. NEXA Voice Engine v2 — controlled hardware shadow mode safety switch

### Status

Implemented.

### What changed

Stage 16 adds a safe development tool and runbook for controlled hardware shadow-mode validation.

New files:

```text
scripts/set_voice_engine_v2_shadow_mode.py
tests/scripts/test_set_voice_engine_v2_shadow_mode.py
docs/validation/voice-engine-v2-shadow-runbook.md

The script can:

print current Voice Engine v2 shadow-mode status,
enable only voice_engine.shadow_mode_enabled,
disable voice_engine.shadow_mode_enabled,
create a backup of config/settings.json,
archive an existing voice_engine_v2_shadow.jsonl log before a new run,
refuse to enable shadow mode if production takeover flags are unsafe.

The script refuses to enable shadow mode unless:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
Why this was needed

Stages 13–15 made real transcript observation possible and added offline validator/inspector tooling.

The next risk is operational: enabling shadow mode manually can lead to accidental config drift.

Stage 16 reduces that risk by making controlled shadow-mode validation explicit, reversible and backup-protected.

What NEXA gains

NEXA gains a safer hardware validation workflow.

This supports the Voice Engine v2 migration without slowing production runtime:

no wake/capture/STT/TTS path is changed,
no Visual Shell runtime path is changed,
no background writer is added,
no production takeover flag is changed,
only shadow telemetry can be enabled for controlled validation.

The runbook also defines a fixed bilingual command set for real hardware checks.

Removed or deprecated legacy path

No legacy path was removed.

The following remain production-primary:

modules/runtime/main_loop/*
modules/devices/audio/input/faster_whisper/*
modules/presentation/visual_shell/controller/voice_command_router.py
modules/core/session/visual_shell_command_lane.py
Source / evidence

This decision is based on:

Stage 13 guarded legacy transcript tap,
Stage 14 shadow telemetry validator,
Stage 15 shadow telemetry inspector,
benchmark acceptance after Stage 15:
command_success_rate=1.0,
fallback_count=0,
p50_speech_end_to_action_ms=50.0,
p95_speech_end_to_action_ms=50.0,
endpoint_delay_ms=260.0,
requirement that Voice Engine v2 must not become production-primary without hardware shadow telemetry.


## 57. NEXA Voice Engine v2 — shadow telemetry route taxonomy cleanup

### Status

Implemented.

### What changed

Stage 17C updates the offline Voice Engine v2 shadow telemetry validator and inspector.

The tooling now treats this pair as semantically equivalent when the intent key matches:

```text
legacy_route=action
voice_engine_route=command
```

This prevents false route mismatch noise for deterministic built-in commands.

The inspector also reads voice_engine_language when the generic language field is missing.

Changed files:

scripts/validate_voice_engine_v2_shadow_log.py
scripts/inspect_voice_engine_v2_shadow_log.py
tests/scripts/test_validate_voice_engine_v2_shadow_log.py
tests/scripts/test_inspect_voice_engine_v2_shadow_log.py
Why this was needed

After Stage 17B, the manual shadow probe successfully wrote telemetry while legacy runtime remained primary.

The validator accepted the record, but the inspector reported:

legacy_route=action
voice_engine_route=command
route_mismatch_records=1

The intent matched correctly:

visual_shell.show_desktop

This was not a functional mismatch. It was a taxonomy difference between legacy route naming and Voice Engine v2 command-first route naming.

What NEXA gains

NEXA gains cleaner shadow telemetry reports before the next hardware run.

This makes the telemetry more useful because real mismatch review can focus on actual behavioural differences:

different intents,
fallback where command should match,
missing transcript,
action execution in shadow mode,
legacy runtime not primary.

It reduces false-positive noise without changing runtime behaviour.

Removed or deprecated legacy path

No legacy runtime path was removed.

No production runtime path was changed.

This stage only changes offline telemetry tooling.

Source / evidence

This decision is based on:

Stage 17B manual probe,
generated shadow telemetry record,
validator/inspector output showing route taxonomy mismatch with matching intent,
Voice Engine v2 migration rule that decisions must be based on useful telemetry, not misleading counters.


## 58. NEXA Voice Engine v2 — first hardware shadow telemetry review

### Status

Implemented.

### What changed

Stage 18 collected the first real Voice Engine v2 shadow telemetry from `python main.py`.

The runtime was started with:

```text
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.shadow_mode_enabled=true
```

The shadow log was created successfully:

var/data/voice_engine_v2_shadow.jsonl

The run collected 6 records.

Why this was needed

Previous stages proved the shadow hook in unit tests and manual probes.

proved that the real hardware runtime path can now feed accepted legacy transcripts into Voice Engine v2 shadow telemetry while legacy runtime remains primary.

What NEXA gains

NEXA now has real transcript evidence from hardware runtime.

The telemetry confirms:

Voice Engine v2 did not execute actions,
legacy runtime remained primary,
shadow mode wrote JSONL telemetry,
command-first intent comparison can run after legacy execution,
real STT/capture problems are visible in the data.
Observed runtime evidence

Safety:

action_executed_records: 0
non_legacy_primary_records: 0
empty_transcript_records: 0
safety_ok: True

Useful matches:

What is your name? -> legacy introduce_self, Voice Engine assistant.identity
What time is it? -> legacy ask_time, Voice Engine system.current_time

Observed STT/capture problems:

show shell -> So shall
show shell -> Show
show shell -> Oka Shell!

Observed runtime issue:

FasterWhisper audio callback status: input overflow

This confirms that the perceived 5–10 second delay is still caused before routing, mainly in wake/capture/endpointing/STT, not in the deterministic Visual Shell router.

Removed or deprecated legacy path

No legacy path was removed.

Legacy wake/capture/STT/TTS/Visual Shell remains production-primary.

Source / evidence

This decision is based on:

controlled hardware shadow run,
generated var/data/voice_engine_v2_shadow.jsonl,
validator output,
inspector output,
runtime logs showing FasterWhisper input overflow,
benchmark gates still accepted.

### 59  Guarded command-first runtime candidates

### Status

Implemented behind config, off by default.

### What changed

NEXA now has a guarded Voice Engine v2 runtime-candidate path for selected deterministic built-in commands.

This is not a full Voice Engine v2 production takeover and it is not the final latency fix. The candidate path still starts after the existing STT transcript is available, so it does not yet solve the main hardware bottleneck in wake/capture/endpointing/FasterWhisper.

The new path validates the live execution contract for selected deterministic commands:

```text
legacy STT transcript
→ Voice Engine v2 command-first comparison
→ allowlist gate
→ runtime candidate execution plan
→ legacy ActionFlow RouteDecision
→ existing ActionFlow execution
```

The first supported runtime candidates are:

assistant.identity mapped to existing legacy action introduce_self
system.current_time mapped to existing legacy action ask_time

The candidate executor does not implement TTS, display, time formatting or assistant response text. Those remain owned by existing ActionFlow handlers:

_handle_introduce_self()
_handle_ask_time()
Why this was needed

Stage 18 hardware shadow telemetry showed that Voice Engine v2 can correctly recognize selected deterministic built-ins, especially identity and current time. However, the real runtime is still slow because the bottleneck is earlier in the path:

wake/capture/endpointing/FasterWhisper

Stage 19 therefore acts as a safe live-candidate proof, not a performance victory claim. It proves that allowlisted deterministic commands can be safely bridged into real execution without enabling the full Voice Engine v2 runtime.

What NEXA gains
A safe bridge from Voice Engine v2 deterministic intent resolution into real ActionFlow execution.
No ad hoc action logic inside interaction_mixin.py.
No LLM route for allowlisted deterministic commands.
Fail-open fallback to legacy for everything uncertain.
Pending confirmations still have priority.
A clear foundation for later moving the command-first recognizer before FasterWhisper.
Safety gates

Runtime candidates can run only when:

voice_engine.runtime_candidates_enabled=true
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
allowlist is non-empty

Default config keeps runtime candidates disabled.

Default allowlist:

assistant.identity
system.current_time

system.exit was added to grammar/intents for telemetry correctness, but it is not supported by the Stage 19 runtime candidate executor and is not in the default allowlist.

Removed or deprecated legacy path

None.

Legacy runtime remains primary. No wake word, audio input, FasterWhisper, TTS or Visual Shell path was removed or replaced.

Source / evidence
Stage 18 hardware shadow telemetry:
What is your name? matched assistant.identity
What time is it? matched system.current_time
exit. was handled by legacy but previously returned Voice Engine v2 fallback/no_match
Runtime observation showed real user-facing delay still around 5–10 seconds because the bottleneck remains before routing.
Existing ActionFlow already owns safe identity/time execution, so Stage 19 bridges into ActionFlow instead of duplicating action logic.
Stage 19 regression tests confirmed disabled config preserves legacy behaviour and enabled runtime candidates only accept allowlisted deterministic commands.


## Stage 20A — Runtime candidate safety switch and runbook

### Status

Implemented.

### What changed

NEXA now has a controlled safety switch for the guarded Voice Engine v2 runtime-candidate path.

New script:

```text
scripts/set_voice_engine_v2_runtime_candidates.py

The script supports:

--status
--enable
--disable

It enables only the Stage 20A runtime candidate allowlist:

assistant.identity
system.current_time

The script refuses to enable runtime candidates unless the runtime remains in the safe migration state:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true

A validation runbook was added:

docs/validation/voice-engine-v2-runtime-candidates-runbook.md
Why this was needed

Stage 19 added the guarded runtime candidate execution contract, but enabling that path manually by editing config would be too risky for hardware testing.

Stage 20A adds a controlled operational switch so runtime candidates can be enabled only when the full Voice Engine v2 production path is still disabled and legacy fallback remains active.

What NEXA gains
Safer hardware validation for Stage 19 runtime candidates.
No manual config editing required for candidate testing.
A fast disable path after testing.
Protection against accidentally enabling full Voice Engine v2 production mode.
Better operational discipline before any live runtime experiment.
Removed or deprecated legacy path

None.

Legacy runtime remains primary. Wake word, audio input, FasterWhisper, TTS and Visual Shell remain unchanged.

Source / evidence
Stage 19 regression tests confirmed that runtime candidates are fail-open and allowlisted.
Stage 18 hardware telemetry showed that identity and current-time commands are useful first candidates.
Project execution rules require guarded config gates, cleanup, tests, architecture notes and no blind production takeover.
Validation



## Stage 20C — Runtime candidate telemetry validator

### Status

Implemented and validated.

### What changed

NEXA now has a validator for guarded Voice Engine v2 runtime-candidate telemetry.

New script:

```text
scripts/validate_voice_engine_v2_runtime_candidate_log.py

The validator reads:

var/data/voice_engine_v2_runtime_candidates.jsonl

and verifies that only safe Stage 20C deterministic candidates are accepted:

assistant.identity
system.current_time

For accepted candidate records, the validator checks:

legacy_runtime_primary=true
llm_prevented=true
route_kind=action
assistant.identity -> introduce_self
system.current_time -> ask_time

It fails if unsupported intents are accepted, especially system.exit.

Why this was needed

Stage 20B added telemetry, but raw JSONL inspection is not enough for repeatable hardware validation.

Before moving command recognition before FasterWhisper, NEXA needs a deterministic validator proving that the current live-candidate bridge accepts only safe allowlisted commands and rejects unsafe or ambiguous transcripts.

What NEXA gains
Repeatable hardware validation for runtime candidates.
Automated safety check against accidental candidate expansion.
Stronger proof that system.exit and Visual Shell ambiguity are not accepted in Stage 20C.
Better confidence before moving toward pre-FasterWhisper command recognition.
No changes to wake word, audio input, FasterWhisper, TTS or Visual Shell.
Removed or deprecated legacy path

None.

Legacy runtime remains primary. This stage validates candidate telemetry only.

Source / evidence
Stage 20A hardware smoke run proved visible behaviour for identity/time and legacy fallback for exit.
Stage 20B telemetry added route-level runtime-candidate records.
Stage 20C validator turns those records into a repeatable safety gate for hardware tests.


## Stage 21A — Pre-FasterWhisper shadow hook

### Status

Implemented behind config, off by default.

### What changed

NEXA now has an observation-only Voice Engine v2 hook immediately before the legacy full STT capture starts in the active command window.

The hook is called before:

```text
_capture_transcript_for_assistant()

inside:

modules/runtime/main_loop/active_window.py

New telemetry path:

var/data/voice_engine_v2_pre_stt_shadow.jsonl

New config:

voice_engine.pre_stt_shadow_enabled=false
voice_engine.pre_stt_shadow_log_path=var/data/voice_engine_v2_pre_stt_shadow.jsonl

Stage 21A is strictly observe-only:

legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false
Why this was needed

Stages 19–20C proved that Voice Engine v2 can safely bridge selected deterministic commands into live runtime after the legacy transcript exists.

However, the real latency bottleneck remains before that point:

wake/capture/endpointing/FasterWhisper

Stage 21A creates the first safe integration point before FasterWhisper without taking over audio, changing microphone ownership, preventing STT or executing actions.

What NEXA gains
First production-safe pre-STT Voice Engine v2 hook.
Evidence path for future realtime audio bus and VAD integration.
No risk to wake word, audio input, FasterWhisper, TTS or Visual Shell.
A clean place to attach future pre-FasterWhisper command recognition.
Better migration structure than patching the legacy router.
Removed or deprecated legacy path

None.

The legacy FasterWhisper path remains primary and unchanged.

Source / evidence
Hardware runtime logs showed the main delay and overflow remain in the wake/capture/endpointing/FasterWhisper path.
Stage 20C validated safe post-STT runtime candidates.
Stage 21A establishes the next migration point before full STT while keeping it observation-only.


## Stage 21B — Pre-STT shadow safety switch

### Status

Implemented and validated.

### What changed

NEXA now has a controlled safety switch for the Stage 21A pre-STT shadow hook.

New script:

```text
scripts/set_voice_engine_v2_pre_stt_shadow.py

The script supports:

--status
--enable
--disable

It safely controls:

voice_engine.pre_stt_shadow_enabled

The script refuses to enable pre-STT shadow unless the runtime remains in a safe migration state:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false

The additional runtime_candidates_enabled=false requirement keeps Stage 21B isolated from the post-STT runtime candidate experiment.

A dedicated runbook was added:

docs/validation/voice-engine-v2-pre-stt-shadow-runbook.md
Why this was needed

Stage 21A added the first hook before legacy full STT capture. Manually editing config/settings.json to test this on hardware would be risky.

Stage 21B adds an operational safety switch so the pre-STT shadow hook can be enabled only in a controlled state and disabled immediately after testing.

What NEXA gains
Safe hardware validation path for the first pre-FasterWhisper hook.
No manual config editing required.
Isolation from runtime candidate experiments.
No risk of accidentally enabling full Voice Engine v2 production mode.
A clean operational path toward future realtime audio bus and VAD shadow integration.
Removed or deprecated legacy path

None.

The legacy wake word, capture, FasterWhisper, TTS, ActionFlow and Visual Shell paths remain primary and unchanged.

Source / evidence
Stage 21A tests confirmed the hook is observe-only and never prevents full STT.
Stage 20C confirmed post-STT runtime candidates are safe but separate.
Runtime logs still show the real bottleneck is before routing, so Stage 21B prepares controlled hardware validation at the pre-STT boundary.
Stage 21B status checks confirmed both pre_stt_shadow_enabled=false and runtime_candidates_enabled=false after validation.


## Stage 22B — Hardware validation of RealtimeAudioBus pre-STT shadow probe

### Status

Validated on Raspberry Pi hardware.

### What changed

Stage 22B validated the Stage 22A realtime audio bus probe in the live NEXA runtime.

The validation temporarily enabled only:

```text
voice_engine.pre_stt_shadow_enabled=true
```

All other Voice Engine v2 takeover flags remained disabled:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false

The runtime was started through:

python main.py

The hardware smoke covered normal live turns:

What is your name?
What time is it?
Exit
Yes.

The pre-STT shadow telemetry wrote four observe-only records to:

var/data/voice_engine_v2_pre_stt_shadow.jsonl
Why this was needed

Stage 22A added an observe-only probe, but it still needed hardware validation inside the real runtime.

The goal was to prove whether the active command runtime exposes a realtime audio bus before FasterWhisper starts, without changing microphone ownership, command execution, wake word behaviour, TTS or Visual Shell state.

This validation is required before any later stage can safely connect a realtime audio source into the pre-STT command-first path.

What NEXA gains

NEXA now has confirmed hardware evidence that the pre-STT boundary is safe for observation.

The validation confirmed that pre-STT shadow telemetry can run during real wake-command and follow-up turns while preserving:

legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false

The validation also confirmed the current expected limitation:

audio_bus_present=false
reason=audio_bus_unavailable_observe_only

This means the RealtimeAudioBus foundation exists in the codebase, but it is not yet wired into the active command runtime.

That is useful evidence. It prevents guessing and keeps the next migration step focused on finding a safe audio source bridge rather than prematurely enabling command-first execution.

Removed or deprecated legacy path

None.

No production path was replaced.

Legacy wake detection, legacy capture, FasterWhisper, TTS, ActionFlow and Visual Shell remained primary.

The generated hardware telemetry and settings backups are validation artifacts only and should not be committed unless a dedicated sample artifact is intentionally added.

Source / evidence

Hardware validation on Raspberry Pi produced:

accepted=true
total_lines=4
observed_records=4
not_observed_records=0
reasons.audio_bus_unavailable_observe_only=4
phases.command=3
phases.follow_up=1
capture_modes.wake_command=3
capture_modes.follow_up=1
issues=[]

Manual inspection confirmed every record contained:

legacy_runtime_primary=True
action_executed=False
full_stt_prevented=False
audio_bus_probe.audio_bus_present=false
audio_bus_probe.probe_error=""

The live runtime still reported:

Runtime state: DEGRADED. Voice mode: half-duplex.
FasterWhisper audio callback status: input overflow

This confirms that Stage 22B is not a final speed fix. It is a safe migration validation step.

Validation
python scripts/set_voice_engine_v2_runtime_candidates.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --status

python scripts/set_voice_engine_v2_pre_stt_shadow.py --enable
rm -f var/data/voice_engine_v2_pre_stt_shadow.jsonl
python main.py

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --status
grep -n -A20 '"voice_engine"' config/settings.json

Expected and observed result:

accepted=true
audio_bus_present=false
reason=audio_bus_unavailable_observe_only
voice_engine.pre_stt_shadow_enabled=false
Follow-up

Stage 22C should not execute actions and should not prevent FasterWhisper.

The next step is a source-level audit for the safest place to expose or attach a realtime audio bus reference to the active runtime metadata.

Stage 22C must answer:

Where does legacy wake/capture currently own microphone input?
Can RealtimeAudioBus be attached without starting a second capture worker?
Can the probe see an existing bus reference without changing audio ownership?
What exact object should expose realtime_audio_bus for Stage 23 shadow-only VAD?

Do not proceed to production takeover.
Do not prevent FasterWhisper.
Do not execute pre-STT actions.


---


## Stage 23A — FasterWhisper callback RealtimeAudioBus shadow tap

### Status

Implemented behind config, disabled by default.

### What changed

Stage 23A added an observe-only realtime audio bus tap to the existing FasterWhisper microphone callback.

New file:

```text
modules/runtime/voice_engine_v2/faster_whisper_audio_bus_tap.py
```

The existing FasterWhisper callback can now copy mono PCM chunks into a runtime-owned AudioBus when this flag is enabled:

voice_engine.faster_whisper_audio_bus_tap_enabled=true

The default remains:

voice_engine.faster_whisper_audio_bus_tap_enabled=false

The runtime builder exposes the bus through runtime metadata only when the tap is enabled:

runtime.metadata["realtime_audio_bus"]

The pre-STT probe from Stage 22A can then detect the bus without starting another microphone stream.

Why this was needed

Stage 22B proved that the pre-STT shadow boundary is safe, but it also showed:

audio_bus_present=false
reason=audio_bus_unavailable_observe_only

Stage 22C confirmed why: the active runtime does not yet expose a realtime audio bus. The current audio path is still owned by the wake gate and FasterWhisper capture path.

Starting AudioCaptureWorker as a second live microphone owner would be unsafe because the runtime already reports half-duplex/degraded behaviour and FasterWhisper callback overflow can appear.

Stage 23A therefore uses the safer migration route:

existing FasterWhisper callback
→ copy PCM chunk
→ publish into RealtimeAudioBus
→ observe-only telemetry

This is not a new command recognition path. FasterWhisper is not being used for fast commands. It only provides an existing microphone callback that can safely mirror audio into the new bus.

What NEXA gains

NEXA now has the first safe bridge between the legacy command capture path and the new Voice Engine v2 realtime audio foundation.

This enables later stages to validate:

RealtimeAudioBus
→ Silero VAD ONNX shadow endpointing
→ Vosk command recognizer shadow path

without taking microphone ownership away from the current runtime.

The stage preserves:

wake word stability
FasterWhisper fallback
TTS
Visual Shell
legacy ActionFlow
Removed or deprecated legacy path

None.

No wake word path was removed.
No FasterWhisper capture path was removed.
No TTS path was changed.
No Visual Shell path was changed.

The tap is disabled by default and exists only as a guarded migration bridge.

Source / evidence

Stage 22B hardware validation produced:

audio_bus_present=false
reason=audio_bus_unavailable_observe_only
legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false

Stage 22C source audit confirmed that the active runtime currently uses existing microphone ownership in the wake gate and FasterWhisper capture path.

Stage 23A follows the safer direction identified by that audit: publish copied PCM from an existing callback instead of starting a second microphone stream.

Validation
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_shadow_tap.py
pytest -q tests/runtime/voice_engine_v2/test_realtime_audio_bus_probe.py
pytest -q tests/runtime/voice_engine_v2/test_pre_stt_shadow.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/realtime
pytest -q tests/devices/audio/command_asr
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice
Follow-up

Stage 23B should add a guarded safety switch for the FasterWhisper audio bus tap and then run hardware validation with:

voice_engine.pre_stt_shadow_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true

Expected Stage 23B result:

audio_bus_present=true
source=runtime.metadata.realtime_audio_bus
legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false

Stage 23B must not execute pre-STT actions, must not prevent FasterWhisper and must not start a second microphone stream.


---


## Stage 24A — Silero VAD shadow endpointing over RealtimeAudioBus

### Status

Implemented behind config, disabled by default.

### What changed

Stage 24A added an observe-only VAD shadow observer over the hardware-validated `RealtimeAudioBus`.

New file:

```text
modules/runtime/voice_engine_v2/vad_shadow.py
```

The observer can read copied PCM frames from the runtime-owned realtime audio bus and run VAD endpointing telemetry without changing the production runtime path.

New config keys were added with safe defaults:

voice_engine.vad_shadow_enabled=false
voice_engine.vad_shadow_max_frames_per_observation=96
voice_engine.vad_shadow_speech_threshold=0.5
voice_engine.vad_shadow_min_speech_ms=120
voice_engine.vad_shadow_min_silence_ms=250

The observer is attached through runtime metadata and is called from the pre-STT shadow boundary. Its result is stored in pre-STT shadow metadata under:

metadata.vad_shadow
Why this was needed

Stage 23B proved that the existing FasterWhisper microphone callback can mirror copied PCM chunks into RealtimeAudioBus without starting a second microphone stream.

Stage 24A starts using that bus for the real Voice Engine v2 target path:

RealtimeAudioBus
→ Silero VAD ONNX endpointing
→ Vosk command recognizer PL/EN
→ CommandIntentResolver
→ fast action

This stage only implements the VAD shadow part.

FasterWhisper is still not used as the fast-command recognizer. FasterWhisper remains the fallback path for full STT, conversation and LLM routing.

What NEXA gains

NEXA now has the first observe-only endpointing layer connected to the realtime audio foundation.

This allows future hardware validation of:

real PCM frames
→ VAD speech/silence decisions
→ speech_started / speech_ended events

without preventing legacy FasterWhisper capture and without executing actions.

This is a key migration step toward reducing the current 5–10 second command latency, because future stages can use VAD endpointing before full STT.

Removed or deprecated legacy path

None.

No wake word path was removed.
No FasterWhisper path was removed.
No TTS path was changed.
No Visual Shell path was changed.
No command-first live execution was enabled.

The VAD shadow observer is disabled by default and remains telemetry-only.

Source / evidence

Stage 23B hardware validation confirmed that RealtimeAudioBus receives real PCM frames from the existing FasterWhisper callback:

audio_bus_present=true
source=runtime.metadata.realtime_audio_bus
frame_count=46
duration_seconds=2.944
snapshot_byte_count=6144
probe_error=""
legacy_runtime_primary=true
action_executed=false
full_stt_prevented=false

Stage 24A unit tests validated the VAD shadow observer in these states:

disabled by default
missing audio bus
audio bus available but no new frames
speech_started and speech_ended event emission
incremental frame reads
fail-open score provider errors
safe config loading
Validation
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_realtime_audio_bus_probe.py
pytest -q tests/runtime/voice_engine_v2/test_pre_stt_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_shadow_tap.py
pytest -q tests/runtime/voice_engine_v2

pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/devices/audio/command_asr
pytest -q tests/scripts/test_set_voice_engine_v2_audio_bus_tap.py
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice

Expected and observed result:

all tests passed
Follow-up

Stage 24B should add a guarded safety switch for VAD shadow hardware validation.

Stage 24B hardware validation should enable only:

voice_engine.pre_stt_shadow_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true
voice_engine.vad_shadow_enabled=true

The expected hardware result is:

audio_bus_present=true
vad_shadow.enabled=true
vad_shadow.observed=true
vad_shadow.action_executed=false
vad_shadow.full_stt_prevented=false
vad_shadow.runtime_takeover=false

Stage 24B must not execute actions, must not prevent FasterWhisper and must not run Vosk yet.


---


## Stage 24B — Guarded VAD shadow safety switch and hardware validation

### Status

Validated on Raspberry Pi hardware.

### What changed

Stage 24B added a guarded safety switch and validator for Voice Engine v2 VAD shadow telemetry.

New scripts:

```text
scripts/set_voice_engine_v2_vad_shadow.py
scripts/validate_voice_engine_v2_vad_shadow_log.py
```
The safety switch controls:

voice_engine.vad_shadow_enabled

It only allows VAD shadow validation when NEXA remains in legacy-primary mode and the required observation dependencies are enabled:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true

The hardware validation enabled:

voice_engine.pre_stt_shadow_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true
voice_engine.vad_shadow_enabled=true

and then disabled all three flags after the smoke run.

Why this was needed

Stage 24A added the VAD shadow observer, but it still needed hardware validation against real runtime audio.

Stage 24B proves that the current migration bridge can safely run:

existing FasterWhisper callback
→ copied PCM into RealtimeAudioBus
→ VAD shadow observer
→ pre-STT telemetry

without changing the production command path.

This keeps the target Voice Engine v2 architecture intact:

Wake word
→ RealtimeAudioBus
→ Silero VAD ONNX endpointing
→ Vosk command recognizer PL/EN
→ CommandIntentResolver
→ fast action

FasterWhisper remains fallback for full STT, conversation and LLM routing.

What NEXA gains

NEXA now has hardware evidence that VAD shadow can observe real audio frames from RealtimeAudioBus.

The validation confirmed:

vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

This means the VAD shadow path is connected and safe.

It also identifies the next engineering target: VAD telemetry tuning and event validation. The hardware run processed frames, but did not emit speech_started or speech_ended events:

total_events_emitted=0
event_types={}

That means Stage 24B validates safe frame processing, but not yet reliable live endpoint event generation.

Removed or deprecated legacy path

None.

No wake word path was removed.
No FasterWhisper path was removed.
No TTS path was changed.
No Visual Shell path was changed.
No command-first execution was enabled.
No Vosk command recognizer was run.

All Stage 24B switches remain disabled by default.

Source / evidence

Pre-STT shadow validator result:

accepted=true
total_lines=5
valid_json_records=5
observed_records=5
not_observed_records=0
reasons.audio_bus_available_observe_only=5
issues=[]

VAD shadow validator result:

accepted=true
vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
total_events_emitted=0
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
reasons.no_new_audio_frames_observe_only=1
reasons.vad_shadow_observed_audio=4
issues=[]

Final safe config after hardware validation:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
Validation
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_pre_stt_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/scripts/test_set_voice_engine_v2_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2

pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/devices/audio/command_asr
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice

Hardware validation:

python scripts/set_voice_engine_v2_runtime_candidates.py --disable
python scripts/set_voice_engine_v2_vad_shadow.py --disable
python scripts/set_voice_engine_v2_audio_bus_tap.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable

python scripts/set_voice_engine_v2_pre_stt_shadow.py --enable
python scripts/set_voice_engine_v2_audio_bus_tap.py --enable
python scripts/set_voice_engine_v2_vad_shadow.py --enable

rm -f var/data/voice_engine_v2_pre_stt_shadow.jsonl
python main.py

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames

python scripts/set_voice_engine_v2_vad_shadow.py --disable
python scripts/set_voice_engine_v2_audio_bus_tap.py --disable
python scripts/set_voice_engine_v2_pre_stt_shadow.py --disable
Follow-up

Stage 24C should improve VAD shadow diagnostics before Vosk is added.

The next stage should not run Vosk yet. It should add telemetry that explains why live hardware produced frames but no endpoint events.

Stage 24C should record at least:

speech_score_min
speech_score_max
speech_score_avg
speech_score_over_threshold_count
silence_frame_count
speech_frame_count
event emission reason

The goal is to confirm whether the missing events are caused by:

Silero score threshold too high
audio frame duration/window mismatch
subscription timing
policy min_speech/min_silence settings
pre-STT observation timing

Stage 24C must remain observe-only and must not execute actions or prevent FasterWhisper.


---


## Stage 24C — VAD shadow score diagnostics and endpoint event validation

### Status

Validated on Raspberry Pi hardware.

### What changed

Stage 24C extended VAD shadow telemetry with score diagnostics.

The VAD shadow metadata now records:

```text
speech_score_min
speech_score_max
speech_score_avg
speech_score_over_threshold_count
speech_frame_count
silence_frame_count
event_emission_reason
```

The validator now supports:

--require-score-diagnostics

This allows hardware validation to distinguish between:

audio bus missing
audio frames missing
VAD score unavailable
scores below threshold
speech frames seen but too short
speech state waiting for silence
endpoint events emitted
Why this was needed

Stage 24B proved that VAD shadow receives real audio frames from RealtimeAudioBus, but hardware telemetry showed:

total_events_emitted=0
event_types={}

Without score diagnostics, NEXA could not determine whether the missing endpoint events were caused by:

threshold too high
wrong audio window size
Silero provider mismatch
insufficient speech duration
insufficient silence duration
subscription timing

Stage 24C made that failure mode measurable.

What NEXA gains

NEXA now has actionable VAD telemetry instead of a vague “no events” result.

The hardware run confirmed:

vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
diagnostics_records=5
speech_score_records=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

The diagnostics identified the current cause:

max_speech_score=0.0
speech_frame_records=0
silence_frame_records=4
event_emission_reasons.all_scores_below_threshold:max=0.000:threshold=0.500=4

This means the realtime audio path is alive, but the current Silero score provider is not producing speech probabilities from live frames.

Removed or deprecated legacy path

None.

No wake word path was removed.
No FasterWhisper path was removed.
No TTS path was changed.
No Visual Shell path was changed.
No command-first execution was enabled.
No Vosk recognizer was run.

Source / evidence

Hardware validation result:

accepted=true
vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
total_events_emitted=0
diagnostics_records=5
speech_score_records=4
speech_frame_records=0
silence_frame_records=4
max_speech_score=0.0
max_speech_frame_count=0
max_silence_frame_count=46
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

The Silero documentation/source describes speech detection as probability-over-threshold per audio chunk and uses a 512-sample window for 16 kHz audio. This supports replacing get_speech_timestamps(...) as the per-frame scoring method with a direct model probability score over 512-sample chunks.

Validation
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_pre_stt_shadow.py
pytest -q tests/runtime/voice_engine_v2

pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/devices/audio/command_asr
pytest -q tests/scripts/test_set_voice_engine_v2_audio_bus_tap.py
pytest -q tests/test_interaction_route_dispatch.py
pytest -q tests/benchmarks/voice

Hardware validation:

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics
Follow-up

Stage 24D should replace the current SileroOnnxVadScoreProvider scoring strategy.

The current implementation uses get_speech_timestamps(...) as a per-frame score source, which is not appropriate for frame-by-frame shadow endpointing.

Stage 24D should use direct Silero model probability scoring over 512-sample windows at 16 kHz, keep the path observe-only, and validate that hardware telemetry produces non-zero speech_score_max during spoken commands.

Stage 24D must not run Vosk yet.


---



## Stage 24D — Silero frame-score provider fix

### Status

Validated on tests / pending Raspberry Pi hardware validation.

### What changed

Stage 24D replaced the VAD shadow score strategy in `SileroOnnxVadScoreProvider`.

The previous implementation used `get_speech_timestamps(...)` as if it were a frame-level score provider. That produced only binary timestamp existence and returned `0.0` for live hardware frames in Stage 24C.

The new implementation loads the Silero ONNX model lazily and calls the model directly over complete Silero scoring windows:

- 512 samples at 16 kHz,
- 256 samples at 8 kHz.

When a `RealtimeAudioBus` frame contains more than one Silero window, the provider scores every complete window and returns the maximum speech probability for the frame-level shadow endpointing policy.

### Why this was needed

Stage 24C proved that:

- RealtimeAudioBus was present,
- VAD shadow observed audio,
- frames were processed,
- safety stayed clean,
- but `max_speech_score` stayed at `0.0`.

That meant the problem was not the audio bus or pre-STT hook. The scoring method was wrong for frame-by-frame endpointing.

### What NEXA gains

NEXA now has a real Silero probability signal in the VAD shadow path.

This is a required step before NEXA can safely move toward:

- fast speech endpointing,
- command-first Vosk recognition,
- lower latency for built-in commands,
- avoiding unnecessary FasterWhisper use for deterministic commands.

The path remains observe-only and does not affect production runtime.

### Removed or deprecated legacy path

Removed from VAD shadow:

- `get_speech_timestamps(...)` as the score source,
- timestamp-existence-as-score behaviour,
- unnecessary score provider timing parameters in default provider construction.

Not removed:

- wake word path,
- FasterWhisper fallback,
- Piper TTS,
- Visual Shell,
- legacy runtime,
- pre-STT shadow safety gates.

### Source / evidence

Evidence from Stage 24C hardware telemetry:

- `audio_bus_present_records=5`
- `frames_processed_records=4`
- `total_frames_processed=184`
- `diagnostics_records=5`
- `speech_score_records=4`
- `max_speech_score=0.0`
- `speech_frame_records=0`
- `unsafe_action_records=0`
- `unsafe_full_stt_records=0`
- `unsafe_takeover_records=0`
- `issues=[]`

Silero examples document direct probability scoring with:

- `speech_prob = model(chunk, SAMPLING_RATE).item()`
- 512-sample windows for 16 kHz,
- 256-sample windows for 8 kHz.

### Validation

Run:

```bash
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents

Hardware validation should confirm:

accepted=true
diagnostics_records>0
speech_score_records>0
max_speech_score>0.0
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Follow-up
```

If hardware validation confirms non-zero Silero probabilities, the next stage should decide whether frame-level max scoring is sufficient or whether VAD shadow should emit window-level decisions for more precise endpoint timing.

Do not enable Vosk, runtime takeover, pre-STT actions or FasterWhisper prevention until VAD shadow is proven stable on hardware.

## Stage 24D — Silero frame-score provider fix

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24D replaced the VAD shadow scoring strategy in `modules/runtime/voice_engine_v2/vad_shadow.py`.

The previous `SileroOnnxVadScoreProvider` used `get_speech_timestamps(...)` as if it were a frame-level score provider. That was incorrect for live frame-by-frame endpointing and caused Stage 24C hardware diagnostics to report real audio frames but always `max_speech_score=0.0`.

The new provider loads the Silero ONNX model lazily and scores audio directly over valid Silero windows:

- 512 samples at 16 kHz,
- 256 samples at 8 kHz.

When a `RealtimeAudioBus` frame contains more than one complete Silero window, the provider scores every complete window and returns the maximum probability for the frame-level shadow endpointing policy.

The implementation also converts NumPy audio windows into tensor input before calling the model, because the real Silero wrapper expects tensor-like audio input.

### Why this was needed

Stage 24C proved that:

- `RealtimeAudioBus` was present,
- VAD shadow observed audio,
- frames were processed,
- safety stayed clean,
- but Silero score diagnostics always stayed at `0.0`.

That meant the issue was not the audio bus, pre-STT hook or FasterWhisper tap. The issue was the scoring strategy inside the VAD shadow observer.

### What NEXA gains

NEXA now has a real Silero probability signal in the pre-STT VAD shadow path.

This is a major step toward the final Voice Engine v2 architecture:

Wake word
→ RealtimeAudioBus
→ Silero VAD ONNX endpointing
→ Vosk command recognizer PL/EN
→ CommandIntentResolver
→ fast action

The system can now observe live speech start and speech end before full FasterWhisper STT, while still remaining safe and observe-only.

This improves the path toward:

- faster endpointing,
- lower command latency,
- reduced dependency on FasterWhisper for deterministic built-in commands,
- measurable pre-STT speech diagnostics,
- safer migration toward command-first recognition.

### Removed or deprecated legacy path

Removed from VAD shadow:

- `get_speech_timestamps(...)` as the frame score source,
- `_get_speech_timestamps`,
- timestamp-existence-as-score behaviour.

Not removed:

- wake word,
- FasterWhisper fallback,
- Piper TTS,
- Visual Shell,
- legacy runtime path,
- pre-STT shadow safety gates.

The legacy voice path remains the primary production path until later Voice Engine v2 stages pass hardware validation.

### Source / evidence

Evidence from Stage 24C hardware telemetry showed:

```text
diagnostics_records=5
speech_score_records=4
speech_frame_records=0
silence_frame_records=4
max_speech_score=0.0
event_emission_reasons:
  no_new_audio_frames_observe_only=1
  all_scores_below_threshold:max=0.000:threshold=0.500=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
```

Evidence from Stage 24D hardware validation showed:

accepted=true
vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
total_events_emitted=8
diagnostics_records=5
speech_score_records=4
speech_frame_records=4
silence_frame_records=4
max_speech_score=0.9999915957450867
max_speech_frame_count=35
max_silence_frame_count=39
event_emission_reasons:
  no_new_audio_frames_observe_only=1
  events_emitted=4
event_types:
  speech_started=4
  speech_ended=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

The implementation follows the Silero VAD direct probability scoring pattern over fixed-size model windows.

Validation

Repository tests passed:

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents

Cleanup checks passed:

grep -R "get_speech_timestamps" -n modules/runtime/voice_engine_v2 tests/runtime/voice_engine_v2
grep -R "_get_speech_timestamps" -n modules/runtime/voice_engine_v2 tests/runtime/voice_engine_v2

No references remained in the Voice Engine v2 VAD shadow path.

Hardware validation passed with:

accepted=true
max_speech_score=0.9999915957450867
speech_started=4
speech_ended=4
issues=[]
Follow-up

Next stage should not enable production takeover yet.

Recommended next step is Stage 24E:

inspect VAD event timing quality,
confirm whether current frame-level max scoring is precise enough,
optionally add window-level event diagnostics,
keep observe-only,
keep FasterWhisper untouched,
keep action execution disabled.

Do not enable Vosk, command execution, pre-STT action dispatch or FasterWhisper prevention until VAD timing is stable and validated.


---


## Stage 24E — VAD shadow timing diagnostics

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24E added timing diagnostics to the Voice Engine v2 VAD shadow observer.

The observer now records timing fields in `VoiceEngineV2VadShadowSnapshot`, including:

- `observation_started_monotonic`
- `observation_completed_monotonic`
- `observation_duration_ms`
- `first_frame_timestamp_monotonic`
- `last_frame_timestamp_monotonic`
- `last_frame_end_timestamp_monotonic`
- `last_frame_age_ms`
- `audio_window_duration_ms`
- `latest_speech_started_lag_ms`
- `latest_speech_ended_lag_ms`
- `latest_speech_end_to_observe_ms`

The VAD shadow validator now supports:

```bash
--require-timing-diagnostics
```
and reports:

timing_diagnostics_records
event_timing_records
max_last_frame_age_ms
max_speech_end_to_observe_ms
Why this was needed

Stage 24D proved that Silero ONNX direct frame scoring works and emits real speech_started and speech_ended events from live audio.

However, NEXA still needed timing evidence to understand whether the VAD shadow path is close enough to real speech end to become the foundation for low-latency command-first endpointing.

Stage 24E does not change runtime behaviour. It adds observability so the next migration step can be based on measured timing instead of assumptions.

What NEXA gains

NEXA now has measurable VAD timing telemetry before production takeover.

This helps identify:

how old the last processed audio frame is when the shadow observer runs,
how long after detected speech end the observer records the event,
whether the current shadow hook is close enough to speech end,
whether a later continuous VAD observation loop is required.

This keeps Voice Engine v2 aligned with the premium latency target while preserving safety.

Removed or deprecated legacy path

No production path was removed.

The following paths remain untouched:

openWakeWord wake path,
FasterWhisper fallback,
Piper TTS,
Visual Shell,
legacy runtime,
runtime candidate takeover,
command execution.

No Vosk command recognizer was enabled.

No FasterWhisper prevention was enabled.

No pre-STT action execution was enabled.

Source / evidence

Repository tests passed:
```bash
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
```
Hardware validation passed with:

accepted=true
vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=4
total_frames_processed=184
total_events_emitted=8
diagnostics_records=5
timing_diagnostics_records=5
event_timing_records=4
speech_score_records=4
speech_frame_records=4
silence_frame_records=4
max_speech_score=0.9999903440475464
max_speech_frame_count=37
max_silence_frame_count=39
max_last_frame_age_ms=4216.1806099975365
max_speech_end_to_observe_ms=4851.140093996946
event_types:
  speech_started=4
  speech_ended=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Validation

Stage 24E passed both repository and Raspberry Pi hardware validation.

Safety remained clean:

unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Follow-up

Next recommended stage is Stage 24F — VAD observe cadence and hook timing audit.

Stage 24E revealed that although Silero detects speech events correctly, the current observation/logging point can be several seconds behind the latest audio frame:

max_last_frame_age_ms=4216.1806099975365
max_speech_end_to_observe_ms=4851.140093996946

Stage 24F should determine whether this lag comes from:

the current pre-STT shadow hook location,
observer call cadence,
legacy FasterWhisper timing,
delayed log snapshot creation,
or the lack of a continuous VAD shadow loop.

Stage 24F must remain observe-only and must not enable Vosk, action execution, runtime takeover or FasterWhisper prevention.


---

## Stage 24F — VAD observe cadence and stale backlog diagnostics

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24F added cadence and backlog diagnostics to the Voice Engine v2 VAD shadow observer.

The VAD shadow snapshot now records:

- `audio_bus_latest_sequence`
- `audio_bus_frame_count`
- `audio_bus_duration_seconds`
- `subscription_next_sequence_before`
- `subscription_next_sequence_after`
- `subscription_backlog_frames`
- `stale_audio_threshold_ms`
- `stale_audio_observed`
- `cadence_diagnostic_reason`

The VAD shadow validator now reports:

- `cadence_diagnostics_records`
- `stale_audio_records`
- `max_subscription_backlog_frames`
- `cadence_diagnostic_reasons`

### Why this was needed

Stage 24E proved that Silero VAD emits correct `speech_started` and `speech_ended` events from live audio, but the timing diagnostics showed that the observation point could be several seconds behind the latest audio frame.

Stage 24F was needed to determine whether this delay came from the VAD scoring itself or from the hook/cadence of the observer.

The result confirmed that the delay is not caused by Silero scoring. The current VAD shadow observer often reads stale audio backlog from the `RealtimeAudioBus`.

### What NEXA gains

NEXA now has evidence that the current shadow observation point is not sufficient for premium low-latency command execution.

This prevents the project from making a wrong architectural decision, such as enabling command-first actions on a stale observer.

NEXA gains:

- clear proof that `RealtimeAudioBus` and Silero scoring work,
- clear proof that current observer cadence can be stale,
- a measurable basis for the next architecture step,
- stronger safety before moving toward command-first recognition.

### Removed or deprecated legacy path

No production path was removed.

The following remained untouched:

- openWakeWord wake path,
- FasterWhisper fallback,
- Piper TTS,
- Visual Shell,
- legacy runtime,
- runtime candidate takeover,
- command execution.

No Vosk command recognizer was enabled.

No FasterWhisper prevention was enabled.

No pre-STT action execution was enabled.

### Source / evidence

Repository tests passed:

```bash
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
```
Hardware validation passed with:

accepted=true
vad_shadow_records=6
enabled_records=6
observed_records=6
audio_bus_present_records=6
frames_processed_records=5
total_frames_processed=230
total_events_emitted=10
diagnostics_records=6
timing_diagnostics_records=6
event_timing_records=5
speech_score_records=5
speech_frame_records=5
silence_frame_records=5
max_speech_score=0.9999943971633911
max_speech_frame_count=36
max_silence_frame_count=39
max_last_frame_age_ms=4326.6113760037115
max_speech_end_to_observe_ms=4895.224224004778
cadence_diagnostics_records=6
stale_audio_records=4
max_subscription_backlog_frames=205
cadence_diagnostic_reasons:
  no_new_audio_frames_at_observe_time=1
  stale_audio_backlog_observed=4
  fresh_audio_backlog_observed=1
event_types:
  speech_started=5
  speech_ended=5
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

Detailed hardware summary showed stale backlog records:

line=2
cadence_reason=stale_audio_backlog_observed
subscription_backlog=175
last_frame_age_ms=4016.925779003941
speech_end_to_observe_ms=4655.539707004209

line=3
cadence_reason=stale_audio_backlog_observed
subscription_backlog=130
last_frame_age_ms=4326.6113760037115
speech_end_to_observe_ms=4895.224224004778

line=4
cadence_reason=stale_audio_backlog_observed
subscription_backlog=205
last_frame_age_ms=108.57535900140647
speech_end_to_observe_ms=1137.6716719969409

line=5
cadence_reason=stale_audio_backlog_observed
subscription_backlog=169
last_frame_age_ms=2788.4571680042427
speech_end_to_observe_ms=3492.757984000491

A later record showed that fresher observation can approach the target range:

line=6
cadence_reason=fresh_audio_backlog_observed
subscription_backlog=145
last_frame_age_ms=130.8389640034875
speech_end_to_observe_ms=963.9108659976046
Validation

Stage 24F passed repository tests and Raspberry Pi hardware validation.

Safety stayed clean:

unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Follow-up

Next recommended stage is Stage 24G — observe-only VAD timing bridge.

Stage 24F proved that the current pre-STT observer can read stale audio backlog. Stage 24G should not enable production takeover. It should add a guarded observe-only mechanism that observes VAD closer to the point where the FasterWhisper audio bus tap publishes PCM.

Stage 24G must remain:

observe-only,
no Vosk yet,
no action execution,
no FasterWhisper prevention,
no runtime takeover,
no second microphone stream,
no wake/TTS/Visual Shell changes.

The goal of Stage 24G is to prove that VAD timing can be observed closer to real speech end before designing the final continuous VAD pipeline.


---


## Stage 24G — observe-only VAD timing bridge

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24G added an observe-only VAD timing bridge around the legacy capture path.

The bridge arms a dedicated VAD shadow subscription before legacy capture starts and observes it after legacy capture completes:

```text
pre-STT shadow hook
→ arm VAD timing bridge at latest AudioBus sequence
→ legacy FasterWhisper capture runs normally
→ observe bridge after capture
→ write VAD timing bridge telemetry

The bridge does not start a second microphone stream and does not run VAD inference inside the audio callback.

New files:

modules/runtime/voice_engine_v2/vad_timing_bridge.py
scripts/set_voice_engine_v2_vad_timing_bridge.py
tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py

Modified files:

modules/runtime/voice_engine_v2/vad_shadow.py
modules/runtime/builder/core.py
modules/runtime/main_loop/active_window.py
modules/shared/config/settings_core/defaults.py
config/settings.json
config/settings.example.json
Why this was needed

Stage 24F proved that the pre-STT VAD shadow observer often read stale audio backlog from the previous capture.

Stage 24G was needed to check whether VAD could be observed closer to the active capture window without taking over production runtime.

What NEXA gains

NEXA now has a safer measurement bridge that can observe audio closer to the current capture.

This gives evidence for the next architecture decision before enabling any command-first runtime behaviour.

Stage 24G showed that:

stale backlog can be avoided by arming a fresh subscription before capture,
post-capture observation reads fresh current-capture audio,
last_frame_age_ms dropped from multi-second stale values to low hundreds of milliseconds,
runtime safety remained clean.
Removed or deprecated legacy path

No production path was removed.

The following remained untouched:

openWakeWord wake path,
FasterWhisper fallback,
Piper TTS,
Visual Shell,
legacy runtime,
runtime candidate takeover,
command execution.

No Vosk command recognizer was enabled.

No FasterWhisper prevention was enabled.

No pre-STT action execution was enabled.

Config changes

Added safe default keys:

"vad_timing_bridge_enabled": false,
"vad_timing_bridge_log_path": "var/data/voice_engine_v2_vad_timing_bridge.jsonl"

The bridge can only be enabled when the safety chain is valid:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true
voice_engine.vad_shadow_enabled=true
voice_engine.vad_timing_bridge_enabled=true
Source / evidence

Repository tests passed:

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/test_core_assistant_import.py

Hardware bridge validation passed with:

accepted=true
vad_shadow_records=4
enabled_records=4
observed_records=4
audio_bus_present_records=4
frames_processed_records=4
total_frames_processed=184
diagnostics_records=4
timing_diagnostics_records=4
speech_score_records=4
max_speech_score=0.3438757061958313
max_last_frame_age_ms=305.7026800015592
cadence_diagnostics_records=4
stale_audio_records=0
cadence_diagnostic_reasons:
  fresh_audio_backlog_observed=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

Detailed bridge summary:

line=1
record_reason=vad_timing_bridge_observed_audio
hook=post_capture
transcript_present=True
cadence_reason=fresh_audio_backlog_observed
stale_audio=False
subscription_backlog=85
frames=46
last_frame_age_ms=187.5616129982518
speech_end_to_observe_ms=None
events=0

line=2
record_reason=vad_timing_bridge_observed_audio
hook=post_capture
transcript_present=True
cadence_reason=fresh_audio_backlog_observed
stale_audio=False
subscription_backlog=74
frames=46
last_frame_age_ms=115.42143300175667
speech_end_to_observe_ms=None
events=0

line=3
record_reason=vad_timing_bridge_observed_audio
hook=post_capture
transcript_present=True
cadence_reason=fresh_audio_backlog_observed
stale_audio=False
subscription_backlog=132
frames=46
last_frame_age_ms=58.60811700404156
speech_end_to_observe_ms=None
events=0

line=4
record_reason=vad_timing_bridge_observed_audio
hook=post_capture
transcript_present=True
cadence_reason=fresh_audio_backlog_observed
stale_audio=False
subscription_backlog=80
frames=46
last_frame_age_ms=305.7026800015592
speech_end_to_observe_ms=None
events=0
Validation

Stage 24G passed repository tests and Raspberry Pi hardware validation.

Safety stayed clean:

unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Follow-up

Stage 24G proved that the VAD timing bridge can avoid stale audio backlog.

However, the bridge did not emit speech events during hardware validation:

total_events_emitted=0
speech_frame_records=0
max_speech_score=0.3438757061958313
event_emission_reasons:
  all_scores_below_threshold

This means the bridge is reading fresh audio, but the observed post-capture frame window appears silence-heavy or misses the strongest speech section.

Next recommended stage is Stage 24H — VAD bridge frame window and score profile diagnostics.

Stage 24H should inspect which part of the current capture is visible to the bridge:

per-observation score distribution,
first/mid/last score samples,
speech-score peak location,
frame source distribution,
whether the bridge only sees tail silence,
whether max_frames_per_observation=96 is enough,
whether the AudioBus ring window or subscription read window drops early speech frames.

Stage 24H must remain:

observe-only,
no Vosk,
no action execution,
no FasterWhisper prevention,
no runtime takeover,
no second microphone stream,
no wake/TTS/Visual Shell changes.

---


## Stage 24H — VAD bridge frame window and score profile diagnostics

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24H added score profile diagnostics to the Voice Engine v2 VAD shadow observer.

The VAD shadow snapshot now records:

- `score_profile_sample_count`
- `score_profile_first_scores`
- `score_profile_middle_scores`
- `score_profile_last_scores`
- `score_profile_peak_score`
- `score_profile_peak_index`
- `score_profile_peak_sequence`
- `score_profile_peak_position_ratio`
- `score_profile_peak_bucket`
- `score_profile_peak_frame_source`
- `score_profile_peak_frame_age_ms`
- `frame_source_counts`

The VAD shadow validator now supports:

```bash
--require-score-profile-diagnostics

and reports:

score_profile_diagnostics_records
max_score_profile_peak_score
score_profile_peak_buckets
score_profile_peak_sources
Why this was needed

Stage 24G proved that the observe-only VAD timing bridge avoids stale audio backlog and reads fresh frames from the current capture.

However, Stage 24G did not emit speech_started or speech_ended events. The maximum Silero score in the bridge path stayed below the speech threshold.

Stage 24H was needed to inspect the shape of the score window and determine whether the bridge sees speech, tail silence, low-energy audio, or the wrong section of the capture.

What NEXA gains

NEXA now has visibility into the score distribution of the VAD bridge window.

This prevents unsafe guesswork such as lowering the Silero threshold blindly.

The system can now report:

where the score peak appears in the observed frame window,
whether the peak is in the first, middle or last third,
which audio source produced the peak,
how old the peak frame is,
whether all observed frames come from the FasterWhisper callback shadow tap,
whether the bridge is seeing real speech or mostly silence.

This keeps Voice Engine v2 aligned with the premium low-latency goal while preserving observe-only safety.

Removed or deprecated legacy path

No production path was removed.

The following remained untouched:

openWakeWord wake path,
FasterWhisper fallback,
Piper TTS,
Visual Shell,
legacy runtime,
runtime candidate takeover,
command execution.

No Vosk command recognizer was enabled.

No FasterWhisper prevention was enabled.

No pre-STT action execution was enabled.

Source / evidence

Repository tests passed:

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/test_core_assistant_import.py

Hardware validation passed with:

accepted=true
vad_shadow_records=4
enabled_records=4
observed_records=4
audio_bus_present_records=4
frames_processed_records=4
total_frames_processed=184
diagnostics_records=4
timing_diagnostics_records=4
score_profile_diagnostics_records=4
speech_score_records=4
speech_frame_records=0
silence_frame_records=4
max_speech_score=0.04741048812866211
max_score_profile_peak_score=0.04741048812866211
max_last_frame_age_ms=278.07171099993866
stale_audio_records=0
cadence_diagnostic_reasons:
  fresh_audio_backlog_observed=4
score_profile_peak_buckets:
  first_third=2
  middle_third=1
  last_third=1
score_profile_peak_sources:
  faster_whisper_callback_shadow_tap=4
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

Detailed hardware score profile showed:

line=1
peak_score=0.04741048812866211
peak_bucket=first_third
peak_source=faster_whisper_callback_shadow_tap
first_scores=[0.04741, 0.013339, 0.013902, 0.011081, 0.007564]
middle_scores=[0.003158, 0.003323, 0.003478, 0.003665, 0.003439]
last_scores=[0.003582, 0.003533, 0.003515, 0.004134, 0.0045]

line=2
peak_score=0.027585595846176147
peak_bucket=first_third
peak_source=faster_whisper_callback_shadow_tap

line=3
peak_score=0.002590775489807129
peak_bucket=middle_third
peak_source=faster_whisper_callback_shadow_tap

line=4
peak_score=0.007506608963012695
peak_bucket=last_third
peak_source=faster_whisper_callback_shadow_tap
Validation

Stage 24H passed repository tests and Raspberry Pi hardware validation.

Safety stayed clean:

unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Follow-up

Next recommended stage is Stage 24I — FasterWhisper tap PCM quality diagnostics.

Stage 24H proved that the VAD bridge reads fresh frames, but those frames have very low Silero scores:

max_score_profile_peak_score=0.04741048812866211
speech_frame_records=0
events_emitted=0

The next stage should inspect the PCM quality published by faster_whisper_callback_shadow_tap:

RMS amplitude,
peak amplitude,
mean absolute amplitude,
zero sample ratio,
sample count,
byte count,
frame duration,
possible clipping,
first/middle/last amplitude samples,
comparison between frames that occur near speech and frames near tail silence.

Stage 24I must remain:

observe-only,
no Vosk,
no action execution,
no FasterWhisper prevention,
no runtime takeover,
no second microphone stream,
no wake/TTS/Visual Shell changes.

Do not lower the VAD threshold as a workaround until PCM quality and frame-window coverage are understood.


---


## Stage 24I — FasterWhisper tap PCM quality diagnostics

### Status

Implemented and validated on Raspberry Pi hardware.

### What changed

Stage 24I added PCM quality diagnostics to the Voice Engine v2 VAD shadow observer.

The VAD shadow snapshot now records:

- `pcm_profile_frame_count`
- `pcm_profile_sample_width_bytes`
- `pcm_profile_total_byte_count`
- `pcm_profile_total_sample_count`
- `pcm_profile_rms`
- `pcm_profile_mean_abs`
- `pcm_profile_peak_abs`
- `pcm_profile_zero_ratio`
- `pcm_profile_near_zero_ratio`
- `pcm_profile_clipping_ratio`
- `pcm_profile_signal_level`
- `pcm_profile_first_frame_rms`
- `pcm_profile_first_frame_peak_abs`
- `pcm_profile_middle_frame_rms`
- `pcm_profile_middle_frame_peak_abs`
- `pcm_profile_last_frame_rms`
- `pcm_profile_last_frame_peak_abs`
- `pcm_profile_peak_frame_index`
- `pcm_profile_peak_frame_sequence`
- `pcm_profile_peak_frame_source`
- `pcm_profile_peak_frame_rms`
- `pcm_profile_peak_frame_peak_abs`
- `pcm_profile_peak_frame_zero_ratio`
- `pcm_profile_peak_frame_age_ms`

The VAD shadow validator now supports:

```bash
--require-pcm-profile-diagnostics

and reports:

pcm_profile_diagnostics_records
max_pcm_profile_rms
max_pcm_profile_peak_abs
max_pcm_profile_mean_abs
max_pcm_profile_zero_ratio
max_pcm_profile_near_zero_ratio
pcm_profile_signal_levels
pcm_profile_peak_sources
Why this was needed

Stage 24H proved that the observe-only VAD timing bridge reads fresh frames from faster_whisper_callback_shadow_tap, but Silero scores stayed below the speech threshold and no VAD events were emitted.

Stage 24I was needed to determine whether the bridge receives real speech energy or mostly silence / near-zero PCM.

What NEXA gains

NEXA now has direct evidence about the quality of the PCM being published into RealtimeAudioBus by the FasterWhisper callback shadow tap.

This prevents unsafe guesswork, especially lowering the VAD threshold blindly.

NEXA can now distinguish between:

stale audio backlog,
fresh but silence-heavy audio,
low-amplitude PCM,
possible scaling problems,
possible wrong capture window,
possible tail-only callback data.
Removed or deprecated legacy path

No production path was removed.

The following remained untouched:

openWakeWord wake path,
FasterWhisper fallback,
Piper TTS,
Visual Shell,
legacy runtime,
runtime candidate takeover,
command execution.

No Vosk command recognizer was enabled.

No FasterWhisper prevention was enabled.

No pre-STT action execution was enabled.

Source / evidence

Repository tests passed:

pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/scripts/test_set_voice_engine_v2_vad_timing_bridge.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/runtime/voice_engine_v2
pytest -q tests/devices/audio/vad
pytest -q tests/devices/audio/realtime
pytest -q tests/core/voice_engine
pytest -q tests/core/command_intents
pytest -q tests/test_core_assistant_import.py

Hardware validation passed with:

accepted=true
vad_shadow_records=5
enabled_records=5
observed_records=5
audio_bus_present_records=5
frames_processed_records=5
total_frames_processed=230
diagnostics_records=5
timing_diagnostics_records=5
score_profile_diagnostics_records=5
pcm_profile_diagnostics_records=5
speech_score_records=5
speech_frame_records=0
silence_frame_records=5
max_speech_score=0.2458934485912323
max_score_profile_peak_score=0.2458934485912323
max_last_frame_age_ms=221.64340599556454
stale_audio_records=0
cadence_diagnostic_reasons:
  fresh_audio_backlog_observed=5
pcm_profile_signal_levels:
  near_silent=5
max_pcm_profile_rms=0.000596
max_pcm_profile_peak_abs=0.004517
max_pcm_profile_mean_abs=0.000409
max_pcm_profile_zero_ratio=0.04316
max_pcm_profile_near_zero_ratio=0.999512
pcm_profile_peak_sources:
  faster_whisper_callback_shadow_tap=5
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]

Detailed hardware PCM summary showed:

line=1
pcm_signal_level=near_silent
pcm_rms=0.00029
pcm_peak_abs=0.00116
pcm_near_zero_ratio=0.999512
score_peak=0.016358017921447754

line=2
pcm_signal_level=near_silent
pcm_rms=0.000375
pcm_peak_abs=0.001648
pcm_near_zero_ratio=0.991827
score_peak=0.05888298153877258

line=3
pcm_signal_level=near_silent
pcm_rms=0.000308
pcm_peak_abs=0.001648
pcm_near_zero_ratio=0.997919
score_peak=0.003821820020675659

line=4
pcm_signal_level=near_silent
pcm_rms=0.000596
pcm_peak_abs=0.004517
pcm_near_zero_ratio=0.917226
score_peak=0.008021056652069092

line=5
pcm_signal_level=near_silent
pcm_rms=0.000329
pcm_peak_abs=0.003326
pcm_near_zero_ratio=0.991487
score_peak=0.2458934485912323
Validation

Stage 24I passed repository tests and Raspberry Pi hardware validation.

Safety stayed clean:

unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
issues=[]
Conclusion

Stage 24I proves that the current VAD timing bridge receives fresh frames, but those frames are near-silent.

This explains why Stage 24G and Stage 24H did not emit speech_started or speech_ended events from the bridge path.

The correct next step is not lowering the Silero threshold.

Follow-up

Next recommended stage is Stage 24J — FasterWhisper callback tap source audit.

Stage 24J should inspect the actual _publish_realtime_audio_bus_shadow_tap(...) source and determine:

what PCM object is being published,
whether it is the same speech PCM used by FasterWhisper,
whether it is normalized float audio converted incorrectly,
whether it is tail/silence after endpointing,
whether the callback provides chunks before, during or after speech,
whether timestamps represent real capture time or publish time,
whether the tap should publish earlier / fuller command-window PCM into RealtimeAudioBus.

Stage 24J must remain:

observe-only,
no Vosk,
no action execution,
no FasterWhisper prevention,
no runtime takeover,
no second microphone stream,
no wake/TTS/Visual Shell changes.

---


## Stage 24J — FasterWhisper callback tap source diagnostics

### Status

Partially implemented / observe-only diagnostics.

### What changed

Stage 24J audited the real FasterWhisper callback tap source and added guarded diagnostics around `faster_whisper_callback_shadow_tap`.

The callback tap now records:
- raw callback mono profile,
- converted int16 mono profile,
- publish timestamp,
- callback `time_info`,
- callback status,
- published byte count,
- conversion warnings,
- recent tap records snapshot.

The FasterWhisper `TranscriptResult.metadata` now includes:
- `realtime_audio_bus_shadow_tap_at_capture_finished`,
- `faster_whisper_stt_capture_audio_profile`.

This allows the VAD timing bridge telemetry to compare:
1. audio published by the live callback tap,
2. audio actually captured and passed into FasterWhisper STT.

### Why this was needed

Stage 24I proved that the VAD timing bridge reads fresh AudioBus frames with `stale_audio_records=0`, but the PCM profile from `faster_whisper_callback_shadow_tap` was near-silent. At the same time, legacy FasterWhisper STT correctly heard real commands such as "What is your name?", "What time is it?", and "Introduce yourself."

The source audit showed that `_publish_realtime_audio_bus_shadow_tap(...)` publishes individual callback frames before they are queued for FasterWhisper capture. The active runtime observes the VAD timing bridge only after `_capture_transcript_for_assistant(...)` returns, which means after capture and FasterWhisper transcription. Because the AudioBus retention window is short and the input stream continues publishing during transcription, the bridge can observe fresh post-capture silence instead of the utterance that FasterWhisper used.

The audit also identified a guarded conversion risk: if the callback ever receives float PCM in `[-1.0, 1.0]`, the current `astype(np.int16)` conversion would collapse most samples to near-zero values. The new diagnostics detect this without changing runtime behaviour.

### What NEXA gains

NEXA gains precise evidence for the next Voice Engine v2 decision:
- whether the callback tap receives real int16 PCM,
- whether float-to-int16 collapse is happening,
- whether the actual STT capture audio is healthy,
- whether the VAD timing bridge is observing post-transcription silence rather than the spoken utterance.

This keeps the migration evidence-based and avoids unsafe threshold tuning or adding another microphone stream.

### Removed or deprecated legacy path

Nothing was removed in Stage 24J.

The existing FasterWhisper callback tap remains observe-only and guarded by:

```text
voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.faster_whisper_audio_bus_tap_enabled=true only during diagnostics
voice_engine.vad_timing_bridge_enabled=true only during diagnostics

No production takeover was introduced.

Source / evidence

Evidence used:

Stage 24I hardware telemetry showing fresh AudioBus frames but near-silent PCM profile.
Runtime source audit of:
modules/devices/audio/input/faster_whisper/backend/capture_mixin.py
modules/devices/audio/input/faster_whisper/backend/core.py
modules/runtime/main_loop/active_window.py
modules/runtime/voice_engine_v2/vad_timing_bridge.py
modules/devices/audio/realtime/audio_bus.py
modules/devices/audio/realtime/audio_frame.py
Validation

Repository tests to validate:

pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_shadow_tap_diagnostics.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Hardware validation should confirm whether:

conversion_warning is empty or reports float-to-int16 collapse,
faster_whisper_stt_capture_audio_profile contains real speech energy,
bridge-observed pcm_profile_signal_level remains near-silent because observation happens after transcription.
Follow-up

If hardware confirms that STT capture audio is healthy but bridge still sees post-transcription silence, Stage 24K should move the observe point closer to capture completion or introduce an observe-only capture-window handoff, without starting a second microphone stream and without executing pre-STT actions.


---


## Stage 24K — FasterWhisper capture-window shadow tap

### Status

Implemented and hardware validated as safe observe-only diagnostics.

### What changed

Stage 24K added an observe-only capture-window shadow tap for FasterWhisper.

A new diagnostic source was introduced:

```text
faster_whisper_capture_window_shadow_tap

This source replays the actual audio buffer that FasterWhisper already captured and used for transcription into RealtimeAudioBus as diagnostic PCM frames.

The implementation records:

capture-window input audio profile,
converted int16 PCM profile,
conversion reason,
published frame count,
published byte count,
diagnostic replay timestamps,
capture/transcription timing metadata.

This does not start a second microphone stream and does not change the production voice route.

Why this was needed

Stage 24I and Stage 24J showed that the VAD timing bridge could read fresh AudioBus frames, but the PCM observed from faster_whisper_callback_shadow_tap was near-silent.

At the same time, legacy FasterWhisper successfully transcribed real commands.

Stage 24K tested whether the problem was Silero VAD, AudioBus, or the specific audio source being observed. The capture-window source confirmed that the actual FasterWhisper capture buffer contains strong speech signal when converted safely to int16 PCM.

What NEXA gains

NEXA now has strong evidence that:

Silero VAD scoring works correctly on NEXA hardware,
RealtimeAudioBus can carry useful speech PCM,
the current near-silent problem is source/timing related, not a VAD threshold problem,
future Voice Engine v2 work should move observation closer to live capture-window timing instead of lowering thresholds or adding another microphone stream.

This protects the premium Voice Engine v2 migration from unsafe fixes and keeps the path toward low-latency command-first routing evidence-based.

Removed or deprecated legacy path

Nothing was removed in Stage 24K.

The capture-window tap is diagnostic-only and remains guarded by existing Voice Engine v2 flags.

The safe default runtime configuration remains:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false

No production takeover was introduced.

Source / evidence

Evidence used:

Stage 24K pytest regression tests.
Fresh hardware run on Raspberry Pi runtime.
var/data/voice_engine_v2_pre_stt_shadow.jsonl
var/data/voice_engine_v2_vad_timing_bridge.jsonl

Hardware validation showed:

accepted=true
issues=[]
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
stale_audio_records=0
source_counts:
  faster_whisper_callback_shadow_tap=133
  faster_whisper_capture_window_shadow_tap=100
capture_window_metadata_records=5
callback_metadata_records=5
max_speech_score=0.999992847442627
pcm_profile_signal_levels:
  high=1
  medium=4
event_emission_reasons:
  events_emitted=5
event_types:
  speech_started=5
  speech_ended=2
Validation

Tests passed:

pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_capture_window_shadow_tap.py
pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_shadow_tap_diagnostics.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Hardware validators passed:

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics \
  --require-timing-diagnostics \
  --require-pcm-profile-diagnostics
Follow-up

Stage 24L should move from diagnostic replay toward a safe live-capture observation bridge.

The next stage must still remain observe-only:

no command execution,
no Vosk yet,
no production takeover,
no second microphone stream,
no FasterWhisper bypass.

The goal of Stage 24L is to expose a live capture-window event or buffer handoff at the moment speech capture completes, so VAD timing diagnostics can observe the same useful PCM without waiting until after full FasterWhisper transcription.


---



## Stage 24L — Pre-transcription capture-window shadow tap

### Status

Implemented and hardware validated as safe observe-only diagnostics.

### What changed

Stage 24L moved the FasterWhisper capture-window shadow tap earlier in the legacy capture flow.

The diagnostic source:

```text
faster_whisper_capture_window_shadow_tap

is now published before _transcribe_audio_candidate(...) runs.

The capture-window diagnostic metadata now records:

publish_stage,
capture_finished_to_publish_start_ms,
transcription_finished_to_publish_start_ms,
capture_window_publish_to_transcription_finished_ms.

This proves whether the same healthy PCM buffer that FasterWhisper uses can be made available to RealtimeAudioBus immediately after capture, before full STT finishes.

Why this was needed

Stage 24K proved that capture-window PCM is healthy and that Silero VAD can score it strongly when it is replayed into RealtimeAudioBus.

However, the VAD timing bridge still observed after FasterWhisper transcription. That meant useful speech frames could expire from the AudioBus retention window or be replaced by later callback frames.

Stage 24L tested whether capture-window audio can be published before transcription without changing production behaviour.

What NEXA gains

NEXA now has evidence that useful speech PCM can be published almost immediately after capture ends.

Hardware validation showed:

capture_window_metadata_records=5
publish_stage_counts.before_transcription=5
max_capture_finished_to_publish_start_ms=2.594

This means the capture-window evidence can be available in a few milliseconds after capture completion.

This is an important step toward Voice Engine v2 because it proves the next bridge does not need to wait for FasterWhisper transcription to begin VAD analysis on the captured command audio.

Removed or deprecated legacy path

Nothing was removed in Stage 24L.

No production takeover was introduced.

No command execution was introduced.

No second microphone stream was introduced.

FasterWhisper remains the legacy STT path.

The safe default runtime configuration remains:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false
Source / evidence

Evidence used:

Stage 24L unit/regression tests.
Fresh Raspberry Pi hardware run.
var/data/voice_engine_v2_pre_stt_shadow.jsonl
var/data/voice_engine_v2_vad_timing_bridge.jsonl

Hardware validation showed:

accepted=true
issues=[]
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
stale_audio_records=0
max_speech_score=0.9999860525131226
capture_window_metadata_records=5
publish_stage_counts.before_transcription=5
max_capture_finished_to_publish_start_ms=2.594
max_capture_window_publish_to_transcription_finished_ms=22348.866
source_counts:
  faster_whisper_callback_shadow_tap=228
  faster_whisper_capture_window_shadow_tap=3

The large capture_window_publish_to_transcription_finished_ms value confirms that the existing post-STT observation point is too late for reliable capture-window VAD evidence. Stage 24M should observe immediately after capture-window publish.

Validation

Tests passed:

pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_capture_window_shadow_tap.py
pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_shadow_tap_diagnostics.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Hardware validators passed:

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics \
  --require-timing-diagnostics \
  --require-pcm-profile-diagnostics
Follow-up

Stage 24M should add an observe-only pre-transcription VAD capture-window observer.

The observer should run immediately after capture-window publish and before FasterWhisper transcription completes.

Stage 24M must remain safe:

no command execution,
no production takeover,
no Vosk yet,
no FasterWhisper bypass,
no second microphone stream,
no threshold lowering.

---


## Stage 24M — Pre-transcription VAD capture-window observer

### Status

Implemented and hardware validated as safe observe-only diagnostics.

### What changed

Stage 24M added an observe-only pre-transcription VAD observer for FasterWhisper capture-window audio.

The FasterWhisper backend can now notify a neutral capture-window observer immediately after publishing:

```text
faster_whisper_capture_window_shadow_tap

The runtime attaches VoiceEngineV2VadTimingBridgeAdapter.observe_after_capture_window_publish(...) as that observer when diagnostic flags are enabled.

This creates a new telemetry hook:

capture_window_pre_transcription

The new flow is:

legacy command capture finishes
→ capture-window PCM is published to RealtimeAudioBus
→ VAD timing bridge observes immediately
→ FasterWhisper transcription continues normally
→ legacy runtime continues normally

This remains observe-only and does not execute any command.

Why this was needed

Stage 24K proved that FasterWhisper capture-window PCM is healthy and that Silero VAD scores it strongly.

Stage 24L proved that the capture-window PCM can be published before FasterWhisper transcription starts, with hardware evidence showing:

max_capture_finished_to_publish_start_ms=2.594
publish_stage_counts.before_transcription=5

However, the existing post_capture VAD timing bridge still observed too late, after FasterWhisper transcription. That caused useful capture-window frames to be mixed with or replaced by later callback frames.

Stage 24M fixed the observation timing problem by observing immediately after capture-window publication and before FasterWhisper transcription completes.

What NEXA gains

NEXA now has safe, measured, pre-transcription VAD evidence on the same captured command audio that FasterWhisper later transcribes.

This is a major Voice Engine v2 milestone because it proves:

useful speech PCM is available before full STT finishes,
Silero VAD can detect speech before FasterWhisper returns text,
the future command-first path can be built before FasterWhisper fallback,
the system does not need a second microphone stream,
the system does not need unsafe Silero threshold lowering,
the current work can proceed toward VAD endpointing and command-first recognition.

This directly supports the target architecture:

Wake word
→ RealtimeAudioBus
→ Silero VAD endpointing
→ command-first recognizer
→ deterministic intent resolver
→ fast action

Fallback only when needed:
→ FasterWhisper
→ router / LLM / conversation
→ Piper TTS
Removed or deprecated legacy path

Nothing was removed in Stage 24M.

The legacy FasterWhisper path remains active.

No production takeover was introduced.

No command execution was introduced.

No Vosk recognizer was added yet.

No second microphone stream was introduced.

The safe default runtime configuration remains:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false
Source / evidence

Evidence used:

Stage 24M unit/regression tests.
Fresh Raspberry Pi hardware run.
var/data/voice_engine_v2_pre_stt_shadow.jsonl
var/data/voice_engine_v2_vad_timing_bridge.jsonl

Hardware validation showed:

accepted=true
issues=[]
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0

hook_counts:
  capture_window_pre_transcription=5
  post_capture=5

reason_counts:
  vad_timing_bridge_pre_transcription_observed_audio=5
  vad_timing_bridge_observed_audio=5

source_counts:
  faster_whisper_callback_shadow_tap=351
  faster_whisper_capture_window_shadow_tap=100

publish_stage_counts:
  before_transcription=5

pre_transcription_records=5
pre_transcription_frames=221
max_pre_transcription_speech_score=0.9999957084655762

The hardware result confirms that the new pre-transcription observer sees strong speech evidence before FasterWhisper transcription completes.

Validation

Tests passed:

pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_capture_window_shadow_tap.py
pytest -q tests/runtime/voice_engine_v2/test_realtime_audio_bus_probe.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Hardware validators passed:

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics \
  --require-timing-diagnostics \
  --require-score-profile-diagnostics \
  --require-pcm-profile-diagnostics
Follow-up

Stage 24N should remain observe-only and start converting the pre-transcription VAD evidence into a structured endpointing candidate.

The next stage should not execute commands yet.

Stage 24N should focus on:

summarising capture_window_pre_transcription VAD events,
extracting speech start/end evidence,
measuring capture-finished-to-VAD-observed latency,
producing a safe endpointing candidate record,
keeping FasterWhisper as fallback.

Stage 24N must still avoid:

command execution,
Vosk integration,
production takeover,
FasterWhisper bypass,
second microphone stream,
threshold lowering.

---



## Stage 24N — Structured pre-transcription VAD endpointing candidate

### Status

Implemented and hardware validated as safe observe-only diagnostics.

### What changed

Stage 24N added a structured endpointing candidate model for Voice Engine v2 VAD diagnostics.

New module:

```text
modules/runtime/voice_engine_v2/vad_endpointing_candidate.py

The new VoiceEngineV2VadEndpointingCandidate converts pre-transcription VAD evidence into structured metadata:

candidate_present
endpoint_detected
reason
source
publish_stage
frames_processed
speech_started
speech_ended
speech_score_max
pcm_profile_signal_level
capture_finished_to_vad_observed_ms
capture_window_publish_to_vad_observed_ms
action_executed
full_stt_prevented
runtime_takeover

The VoiceEngineV2VadTimingBridgeAdapter now writes this candidate into telemetry metadata for the capture_window_pre_transcription hook.

The stage remains observe-only. It does not execute commands, prevent full STT, bypass FasterWhisper, or take over runtime.

Why this was needed

Stage 24M proved that NEXA can observe Silero VAD on FasterWhisper capture-window audio before FasterWhisper transcription completes.

Stage 24N was needed to convert that raw VAD evidence into a stable, testable endpointing candidate that future Voice Engine v2 stages can reason about safely.

Without a structured candidate, future work would need to inspect raw telemetry dictionaries directly, which would increase coupling and make the migration harder to maintain.

What NEXA gains

NEXA now has a clean structured bridge between pre-transcription VAD evidence and the future command-first voice pipeline.

This gives NEXA:

a safe endpointing candidate before full STT completes,
measurable capture-to-VAD latency,
explicit speech start/end evidence,
clear safety fields proving no runtime takeover,
a stable architecture point for future command-first recognition,
evidence that useful speech information is available before FasterWhisper returns text.

This supports the target Voice Engine v2 architecture:

Wake word
→ RealtimeAudioBus
→ Silero VAD endpointing
→ command-first recognizer
→ deterministic intent resolver
→ fast action

Fallback only when needed:
→ FasterWhisper
→ router / LLM / conversation
→ Piper TTS
Removed or deprecated legacy path

Nothing was removed in Stage 24N.

No production takeover was introduced.

No command execution was introduced.

No Vosk recognizer was added.

No second microphone stream was introduced.

FasterWhisper remains the legacy STT fallback path.

The safe default runtime configuration remains:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false
Source / evidence

Evidence used:

Stage 24N unit/regression tests.
Fresh Raspberry Pi hardware run.
var/data/voice_engine_v2_pre_stt_shadow.jsonl
var/data/voice_engine_v2_vad_timing_bridge.jsonl

Hardware validation showed:

accepted=true
issues=[]
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0

hook_counts:
  capture_window_pre_transcription=6
  post_capture=6

candidate_records=6
candidate_present_records=6
endpoint_detected_records=5

candidate_reason_counts:
  endpoint_detected=5
  speech_not_ended_yet=1

candidate_source_counts:
  faster_whisper_capture_window_shadow_tap=6

candidate_publish_stage_counts:
  before_transcription=6

max_speech_score=0.9999922513961792
max_capture_finished_to_vad_observed_ms=228.085
max_capture_window_publish_to_vad_observed_ms=226.232

The single speech_not_ended_yet record is acceptable for this observe-only stage because the candidate model is expected to represent incomplete endpoint states safely.

Validation

Tests passed:

pytest -q tests/runtime/voice_engine_v2/test_vad_endpointing_candidate.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/devices/audio/input/faster_whisper/test_realtime_audio_bus_capture_window_shadow_tap.py
pytest -q tests/runtime/voice_engine_v2/test_realtime_audio_bus_probe.py
pytest -q tests/runtime/voice_engine_v2/test_faster_whisper_audio_bus_tap.py
pytest -q tests/runtime/voice_engine_v2/test_vad_shadow.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Hardware validators passed:

python scripts/validate_voice_engine_v2_pre_stt_shadow_log.py \
  --log-path var/data/voice_engine_v2_pre_stt_shadow.jsonl \
  --require-observed

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics \
  --require-timing-diagnostics \
  --require-score-profile-diagnostics \
  --require-pcm-profile-diagnostics
Follow-up

Stage 24O should remain observe-only and add an endpointing candidate validator/summary tool.

The next stage should focus on:

validating endpointing candidates from telemetry logs,
summarising candidate counts, endpoint detection rate, and latency,
detecting unsafe candidate states,
separating pre-transcription candidate evidence from post-capture legacy bridge evidence.

Stage 24O must still avoid:

command execution,
Vosk integration,
production takeover,
FasterWhisper bypass,
second microphone stream,
threshold lowering.

---

## Stage 24O — Endpointing candidate validator

### Status

Implemented and validated.

### What changed

Stage 24O added a dedicated validation tool for Voice Engine v2 pre-transcription VAD endpointing candidates.

New script:

```text
scripts/validate_voice_engine_v2_endpointing_candidates.py

New tests:

tests/scripts/test_validate_voice_engine_v2_endpointing_candidates.py

The validator reads:

var/data/voice_engine_v2_vad_timing_bridge.jsonl

and validates metadata.endpointing_candidate records.

It reports:

candidate count,
candidate present count,
endpoint detected count,
candidate reasons,
candidate sources,
candidate publish stages,
signal level counts,
max speech score,
max frames processed,
latency metrics,
unsafe top-level records,
unsafe candidate records.

The validator supports strict requirements:

--require-candidates
--require-candidate-present
--require-endpoint-detected
--require-pre-transcription-hook
--require-capture-window-source
--require-before-transcription-stage
--require-latency-metrics
Why this was needed

Stage 24N introduced structured pre-transcription VAD endpointing candidates.

Stage 24O was needed so future Voice Engine v2 stages can validate those candidates automatically instead of manually inspecting JSONL telemetry.

This prevents unsafe progress based on assumptions and gives NEXA a repeatable acceptance gate before moving toward command-first recognition.

What NEXA gains

NEXA now has an automated evidence gate for pre-transcription endpointing candidates.

This helps confirm:

endpointing candidates exist,
candidates are produced before transcription,
candidates come from faster_whisper_capture_window_shadow_tap,
speech endpoint evidence is present,
latency metrics are recorded,
no command action was executed,
full STT was not prevented,
runtime was not taken over.

This keeps Voice Engine v2 migration measurable and safe.

Removed or deprecated legacy path

Nothing was removed in Stage 24O.

No runtime path was changed.

No production takeover was introduced.

No Vosk recognizer was added.

No command execution was introduced.

No FasterWhisper bypass was introduced.

The safe default runtime configuration remains:

voice_engine.enabled=false
voice_engine.mode=legacy
voice_engine.command_first_enabled=false
voice_engine.fallback_to_legacy_enabled=true
voice_engine.runtime_candidates_enabled=false
voice_engine.pre_stt_shadow_enabled=false
voice_engine.faster_whisper_audio_bus_tap_enabled=false
voice_engine.vad_shadow_enabled=false
voice_engine.vad_timing_bridge_enabled=false
Source / evidence

Evidence used:

Stage 24O pytest validation.
Stage 24N fresh Raspberry Pi hardware telemetry.
var/data/voice_engine_v2_vad_timing_bridge.jsonl.

Validator result:

accepted=true
issues=[]
candidate_records=6
candidate_present_records=6
endpoint_detected_records=5
candidate_reason_counts:
  endpoint_detected=5
  speech_not_ended_yet=1
candidate_source_counts:
  faster_whisper_capture_window_shadow_tap=6
candidate_publish_stage_counts:
  before_transcription=6
candidate_signal_level_counts:
  high=4
  medium=2
max_speech_score=0.9999922513961792
max_capture_finished_to_vad_observed_ms=228.085
max_capture_window_publish_to_vad_observed_ms=226.232
unsafe_action_records=0
unsafe_full_stt_records=0
unsafe_takeover_records=0
unsafe_candidate_action_records=0
unsafe_candidate_full_stt_records=0
unsafe_candidate_takeover_records=0
Validation

Tests passed:

pytest -q tests/scripts/test_validate_voice_engine_v2_endpointing_candidates.py
pytest -q tests/runtime/voice_engine_v2/test_vad_endpointing_candidate.py
pytest -q tests/runtime/voice_engine_v2/test_vad_timing_bridge.py
pytest -q tests/scripts/test_validate_voice_engine_v2_vad_shadow_log.py
pytest -q tests/test_core_assistant_import.py

Endpointing candidate validator passed:

python scripts/validate_voice_engine_v2_endpointing_candidates.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-candidates \
  --require-candidate-present \
  --require-endpoint-detected \
  --require-pre-transcription-hook \
  --require-capture-window-source \
  --require-before-transcription-stage \
  --require-latency-metrics

VAD shadow validator passed:

python scripts/validate_voice_engine_v2_vad_shadow_log.py \
  --log-path var/data/voice_engine_v2_vad_timing_bridge.jsonl \
  --require-enabled \
  --require-observed \
  --require-audio-bus-present \
  --require-frames \
  --require-score-diagnostics \
  --require-timing-diagnostics \
  --require-score-profile-diagnostics \
  --require-pcm-profile-diagnostics
Follow-up

Stage 24P should remain observe-only and start preparing a command-recognition readiness gate.

The next stage should not add Vosk yet unless explicitly scoped as a disabled adapter.

Stage 24P should focus on:

separating pre-transcription candidate telemetry from post-capture legacy bridge telemetry,
defining readiness criteria for command-first recognition,
measuring candidate quality per turn,
preparing a safe interface for future command ASR input.

Stage 24P must still avoid:

command execution,
production takeover,
FasterWhisper bypass,
second microphone stream,
threshold lowering.

---
