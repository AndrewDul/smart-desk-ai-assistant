# Troubleshooting Log



## Issue 001 - USB microphone captures too much noise
**Date:** 2026-03-31  
**Area:** audio  
**Status:** partial  

**Problem**  
The connected USB microphone worked, but voice recognition was not stable.

**Symptoms**  
- assistant sometimes needed repeated commands
- background noise affected speech recognition
- recognition quality was inconsistent

**What I tested**  
- microphone connected and detected
- speaker output confirmed
- speech recognition tested with Vosk
- multiple spoken command attempts tested

**Root cause**  
The microphone appears to capture too much environmental noise and is not ideal for clean command recognition.

**Fix applied**  
No final hardware fix yet. Software recognition was improved enough to begin testing commands.

**Result**  
Voice commands work, but not as reliably as desired.

**Follow-up**  
Possible improvement:
- buy a better microphone or USB headset
- tune gain and microphone placement
- test grammar-restricted recognition mode again

---

## Issue 002 - OLED did not show output with earlier display module
**Date:** 2026-04-01  
**Area:** OLED / software  
**Status:** resolved  

**Problem**  
OLED was not showing output when the earlier animated display file was used.

**Symptoms**  
- OLED remained blank
- minimal display test worked
- larger display module version failed

**What I tested**  
- confirmed OLED worked with a shorter test display file
- compared working and non-working versions of `display.py`
- checked display initialization logic
- replaced the OLED import and simplified drawing logic

**Root cause**  
The previous display implementation was less reliable. The working version used a simpler initialization path and a simpler rendering approach.

**Fix applied**  
`display.py` was rebuilt on top of the working OLED initialization and then extended again with safer animation logic.

**Result**  
OLED output worked again and could be extended back toward animated display behaviour.

**Follow-up**  
If OLED issues return later:
- test with a minimal OLED text screen first
- confirm I2C device detection
- confirm the exact OLED driver class

---

## Issue 003 - Voice recognition test failed because Python could not import modules
**Date:** 2026-04-01  
**Area:** software / project structure  
**Status:** resolved  

**Problem**  
The voice recognition test file failed with a module import error.

**Symptoms**  
- `ModuleNotFoundError: No module named 'modules'`

**What I tested**  
- confirmed working directory
- added `__init__.py` files
- launched the test using module mode instead of direct file execution

**Root cause**  
The test was launched in a way that did not correctly treat the project structure as a package.

**Fix applied**  
Used:
- `touch modules/__init__.py`
- `touch tests/__init__.py`
- `python -m tests.test_voice_commands`

**Result**  
The test loaded correctly and Vosk initialized.

**Follow-up**  
Keep test execution consistent and package-aware.

---

## Issue 004 - OLED animation and text overlay need continued tuning
**Date:** 2026-04-01  
**Area:** OLED / UX  
**Status:** open  

**Problem**  
The OLED now works, but the display behaviour still needs polish.

**Symptoms**  
- eye shape and motion may still need refinement
- animation timing may need adjustment
- text overlays should remain readable and then cleanly return to idle eyes

**What I tested**  
- simple OLED text output
- animated idle mode
- menu/status overlays with timed return

**Root cause**  
This is not a fault anymore, but an expected refinement stage.

**Fix applied**  
Current display module supports both animation and text overlays.

**Result**  
The OLED is now usable for both assistant animation and temporary information screens.

**Follow-up**  
Improve:
- eye design
- blink behaviour
- expression variety
- menu readability


## Troubleshooting Log – Voice System Migration

### 005 `ModuleNotFoundError: No module named 'modules'

**Symptom**  
Running the test file directly caused Python to fail when importing internal project modules.

**Cause**  
The test was executed as a standalone file from the `tests` directory, so the project root was not added to the Python path.

**Fix**  
The test file was updated to insert the project root into `sys.path`, and tests were also run using:

python -m tests.test_voice_commands
## 2. `whisper-cli not found at: whisper.cpp/build/bin/whisper-cli`

### Symptom
The Whisper input module failed during startup because it could not find the Whisper CLI binary.

### Cause
`whisper.cpp` had been cloned but not built yet.

### Fix
`whisper.cpp` was built locally using CMake so that `build/bin/whisper-cli` became available.

---

## 006 `cmake: command not found`

### Symptom
The build process for `whisper.cpp` could not start.

### Cause
CMake was not installed on the Raspberry Pi system.

### Fix
Required build tools were installed before compiling `whisper.cpp`.

---

## 007 `PortAudioError: Invalid sample rate [PaErrorCode -9997]`

### Symptom
The USB microphone failed to open when recording started.

### Cause
The selected microphone did not accept the fixed `16000 Hz` sample rate used by the first version of the audio input layer.

### Fix
The audio input module was updated to:
- detect the selected input device
- inspect supported sample rates
- choose a valid sample rate automatically

This resolved the issue and the microphone was successfully opened at `44100 Hz`.

---

## 008 Wrong transcript from short command with language auto mode

### Symptom
A short Polish utterance was transcribed into unrelated text in another script.

### Cause
Very short speech inputs are harder for auto language detection and may produce incorrect results.

### Fix / Outcome
Additional practical testing showed that the Whisper setup still performed well overall in both Polish and English, so the current system was kept.

This remains a known limitation for very short inputs.

---

## 008 Main application still used Vosk instead of Whisper

### Symptom
The application crashed on startup with a Vosk model error even though Whisper had already been introduced.

### Cause
The updated `assistant_logic.py` had not been saved, so the old `VoiceInput` / Vosk path was still active.

### Fix
The file was saved correctly and the assistant was re-run using the Whisper path.

---

## 009 `AttributeError: 'CoreAssistant' object has no attribute 'handle_command'`

### Symptom
The application started, speech was transcribed, but then the assistant crashed after receiving the transcript.

### Cause
The `handle_command` method was missing from the updated assistant logic class.

### Fix
The missing method was added back to `CoreAssistant`.

---

## 010 `intent_parser.py` content was incomplete after copy/paste

### Symptom
The file appeared much shorter than expected and was missing parts of the bilingual parsing logic.

### Cause
The code had been sent in large blocks and part of it was cut during copy/paste.

### Fix
The migration process was changed to a file-by-file approach to reduce truncation risk and make verification easier.

---

## 011`espeak-ng` voice quality was too robotic

### Symptom
Speech output worked technically, but the voice sounded too artificial and too synthetic for the intended user experience.

### Cause
`espeak-ng` is lightweight and practical for offline use, but it is not a natural-sounding neural TTS engine.

### Current Status
The voice output layer was improved to support:
- separate Polish and English voices
- language-dependent output
- female voice variants

However, the output is still considered temporary.

### Planned Improvement
Replace the current TTS layer with a more natural local speech engine in a future iteration.

---

### Current Stable Outcome

At the end of this troubleshooting stage, the following were working:
- `whisper.cpp` installed and running locally
- microphone input working correctly
- automatic supported sample rate selection
- successful Polish and English speech transcription
- natural intent parsing for several command types
- localized responses by language
- introduction intent
- time query intent
- menu/help localisation
- follow-up question for capturing user name


## 012. GitHub push rejected because of large Whisper model file

### Symptom
The repository could not be pushed to GitHub even though the local commit completed successfully.

GitHub rejected the push with an error explaining that:

- `models/ggml-base.bin` was too large
- the file exceeded GitHub's `100 MB` file size limit
- the push was declined by the remote pre-receive hook

### Cause
The local Whisper model file `ggml-base.bin` had been included in version control history.

This file is required locally for speech recognition, but it should not be committed to the repository because it is a large runtime dependency rather than source code.

A second local issue was that the embedded `whisper.cpp/` folder also appeared as an untracked local dependency workspace and was not intended to be committed as part of the main project repository.

### Fix
The repository was cleaned so that local Whisper runtime artifacts were excluded from version control.

The following actions were taken:
- added `models/ggml-base.bin` to `.gitignore`
- added `models/ggml-silero-v6.2.0.bin` to `.gitignore`
- added `whisper.cpp/` to `.gitignore`
- removed the Whisper model files from Git tracking
- reset local staged history back to `origin/main`
- re-staged only the intended project files
- prepared a clean replacement commit without oversized binary assets

### Outcome
The project structure is now cleaner and better separated between:
- source code and documentation that belong in the repository
- local runtime model files and external build folders that should stay on the development machine only

This also established a better rule for future development:
large local AI models and third-party build directories should not be committed directly to the main GitHub repository.


## 013 Recent Development Issues and Fixes

### 1. `IndentationError` in `assistant_logic.py`

**Problem**  
After modifying the boot flow, Python raised an `IndentationError` near the `boot()` function.

**Cause**  
The contents of the `boot()` function were pasted with incorrect indentation, so Python interpreted the function body incorrectly.

**Fix**  
The method indentation was corrected so that:
- `boot()` is defined at class level
- all statements inside `boot()` are properly indented

---

### 2. `AttributeError: 'CoreAssistant' object has no attribute 'boot'`

**Problem**  
When running `python main.py`, the program raised:

AttributeError: 'CoreAssistant' object has no attribute 'boot'


### Cause
The startup logic was accidentally pasted inside `__init__()` instead of being defined as a separate class method. As a result, the object executed startup behaviour during construction, but no actual `boot()` method existed.

### Fix
The boot logic was moved out of `__init__()` and restored as a separate method:

def boot(self) -> None:
## 014 Assistant responded to silence or blank audio

### Problem
The assistant sometimes responded with “I did not understand” even when the user said nothing.

### Cause
Blank recogniser outputs, silence markers, or low-value transcripts were reaching the command handler.

### Fix
Input filtering was added in the main loop and Whisper input layer to ignore:

- `None`
- blank strings
- silence markers such as `[BLANK_AUDIO]`
- low-value filler noise

This made the assistant remain silent when no meaningful speech was detected.

---

## 015 OLED overlays replaced the eye animation permanently

### Problem
Displayed information such as reminders or time screens could interrupt the eye animation without clearly returning to the default visual state.

### Cause
The display logic needed a dedicated overlay lifecycle.

### Fix
The OLED renderer was redesigned so that:

- the animated eyes are the default state
- information is shown only as a timed overlay
- after the overlay expires, the display automatically returns to the eyes

---

## 016 Startup speech happened too early

### Problem
The assistant started speaking immediately after the boot screen appeared, which felt abrupt.

### Cause
The voice greeting was triggered without a visual pause after the startup screen.

### Fix
The startup sequence was redesigned:

1. show `DevDul`
2. return to the eye animation
3. wait briefly
4. speak the English greeting

This created a more polished startup experience.

---

## 017 Conversational flow was too command-based

### Problem
Early versions of the assistant behaved like a rigid command parser rather than a conversational assistant.

### Cause
The original design expected single-shot commands and had limited support for follow-up questions.

### Fix
Temporary follow-up states were introduced for:

- name capture
- memory consent
- timer duration
- focus duration
- break duration
- OLED display confirmation
- post-focus break offer

This allowed the assistant to support multi-step conversational flows.

---

## 018 Timer and session state consistency

### Problem
Focus, break, and timer states could become difficult to manage when stopping or finishing sessions.

### Cause
State cleanup and timer lifecycle handling needed clearer separation.

### Fix
The timer logic was updated so that:

- only one session can run at a time
- stopping resets the timer state cleanly
- finishing triggers the correct callback
- focus and break states are updated consistently in the assistant session state

---

## 019 Memory recall needed more flexible matching

### Problem
Natural queries such as “Where are my keys?” did not always match previously stored facts unless the wording was identical.

### Cause
Simple exact matching was too strict for spoken interaction.

### Fix
The memory module was improved with:

- text cleanup
- key normalization
- possessive prefix stripping
- limited plural/singular matching
- fuzzy matching based on token overlap and similarity

This improved recall reliability in both English and Polish.

---

# Hardware Change Troubleshooting Notes

## Overview

During development I replaced my original OLED display and older microphone setup with a new LCD display and a new USB microphone array.

This upgrade improved the hardware, but it also caused several integration problems that I had to solve step by step.

This file records the main problems I had and how I worked through them.

---

## 020 New microphone detected but first test command was wrong

After connecting the new microphone, I checked the capture devices with:

`arecord -l`

The system showed:

- **card 2**
- **device 0**
- **reSpeaker XVF3800 4-Mic Array**

At first I used the wrong device number in the recording command, so the test failed.

### Problem
I tried:
- `plughw:4,0`

but my real microphone card was:
- `plughw:2,0`

### Result
After correcting the card number, the microphone recording command worked.

---

## 021 No sound during playback caused confusion

At one point I could record audio, but I could not hear playback.

This made it look like the microphone might not be working, but later I realised that the problem was related to audio output settings, not the microphone itself.

### What happened
- recording worked
- playback seemed silent
- YouTube audio was also silent

### Conclusion
This was not a microphone problem.
It was a system audio output issue.

The important result was that the new microphone itself was working correctly.

---

## 022. ReSpeaker microphone quality was much better than the old one

After testing the ReSpeaker properly, I confirmed that it was clearly better than the previous microphone.

### Result
- very low noise
- much cleaner voice capture
- much better overall input quality

This was one of the most successful hardware upgrades in the project.

---

## 023. Python import problem when testing the display

When I tried to run the LCD test script, Python failed with:

`ModuleNotFoundError: No module named 'modules'`

### Cause
The test script was being run from inside the `scripts` folder path and Python was not resolving the project root properly.

### Fix
I updated the test scripts so they explicitly added the project root to `sys.path`.

### Result
The test scripts could import project modules correctly.

---

## 024 LCD failed because GPIO support was missing

When I first tried the new display, I got an error like:

`No module named 'RPi'`

### Cause
The display libraries needed Raspberry Pi GPIO support, but it was not available in the environment yet.

### What I installed
I had to install and fix:
- `rpi-lgpio`
- `spidev`
- `luma.lcd`
- `gpiozero`
- required system packages like `swig`

### Result
After fixing GPIO-related dependencies, the display stack could initialise further.

---

## 025 SPI was enabled correctly, so hardware bus was not the problem

I checked the SPI devices and confirmed that SPI was enabled correctly.

### Result
The system showed:
- `/dev/spidev0.0`
- `/dev/spidev0.1`

This meant SPI itself was available and working.

---

## 026 `luma.lcd` did not work properly with this 240x320 display

I tested the new LCD using a `luma.lcd` based approach.

### Result
The display partially worked, but the image was wrong:
- noise on the side
- flashing at the top
- incomplete or corrupted output

### Conclusion
This was not a wiring problem.
It looked like a compatibility or rendering issue with this specific 240x320 panel and that backend.

---

## 027 Generic `st7789` testing also did not solve it

I also tested another direct `st7789` path.

### Result
That also did not give me a stable correct display.

### Conclusion
Not every ST7789 library behaves correctly with every panel.
The fact that the panel uses ST7789 does not automatically mean every Python driver will work properly with it.

---

## 028 The official Waveshare vendor demo proved the hardware was good

The most important test was the official Waveshare Python demo for the 2inch LCD.

### Result
The vendor demo displayed correctly.

This proved:
- the LCD hardware was good
- the wiring was correct
- SPI communication was working
- the problem was mainly in software integration, not in the physical hardware

This was the key turning point in the troubleshooting process.

---

## 029 Missing `gpiozero` blocked the vendor demo at first

When I tried the Waveshare Python demo, it first failed because `gpiozero` was missing.

### Fix
I installed `gpiozero` into the project environment.

### Result
After that, the vendor demo could run.

---

## 030 Vendor demo image path warning was not a hardware failure

During the vendor demo, one image file was missing:

`[Errno 2] No such file or directory: '../pic/LCD_2inch4_1.jpg'`

### Meaning
This did not mean the LCD failed.
The important part was that the drawing steps before that already showed the screen working.

---

## 031 Custom runtime wrapper for the LCD was harder than expected

After proving the vendor demo worked, I tried to integrate the Waveshare LCD into my own runtime display code.

This led to several problems:
- black screen most of the time
- only seeing a fragment of the eyes for a moment
- wrong orientation
- incorrect width / height assumptions
- display update timing issues
- repeated frame rendering problems

### What I learned
This display is more sensitive than the old OLED.
It cannot just be treated as a drop-in replacement.

The LCD path needs a display-specific rendering approach.

---

## 032 The direct custom vendor-based test helped isolate the issue

I created direct tests that bypassed the old display wrapper and used the Waveshare driver path more directly.

These tests helped me understand:
- how the vendor path behaves
- how the image buffer behaves
- what kind of rotation / orientation was needed
- that repeated rendering is more fragile than simple static vendor demo drawing

This gave me a better basis for the next display integration work.

---

## Main Lessons

### What worked well
- replacing the microphone
- detecting the ReSpeaker
- recording audio at 16 kHz
- verifying that the LCD hardware and wiring were correct through the vendor demo

### What was difficult
- getting the LCD to work through generic Python display libraries
- integrating the LCD into my own display runtime
- handling orientation and update behaviour correctly

### Most important conclusion
The microphone upgrade was successful and stable.

The LCD hardware upgrade was also successful physically, but software integration for the display required much more work than expected.
The official vendor driver was the most reliable proof that the display itself was working.


## 033. Polish and English recognition was weak with the base Whisper model

### Problem

The assistant was not handling Polish and English speech well enough in real use.

English sometimes worked, but Polish was much worse, especially for short commands like:

- co potrafisz
- która jest godzina
- idź spać
- wyłącz asystenta

Sometimes the assistant understood part of the sentence, sometimes it guessed something completely wrong, and sometimes it mixed languages in the response.

### What I tried first

At first I tried to improve this through:

- parser logic updates
- better language detection rules
- new command phrases
- follow-up flow improvements
- confirmation logic improvements
- auto / English / Polish comparison logic

Some of these changes helped a bit, but overall they did not solve the real problem well enough.

### Real cause

The main issue was not only parser logic.  
The bigger issue was the speech-to-text quality itself.

The Whisper base model was too weak for the kind of bilingual assistant I wanted to build. It was especially weak for short Polish commands.

### Fix

I changed the Whisper model from `base` to `small`.

After this change the improvement was immediate and clearly visible. The assistant started understanding both Polish and English much better, and the main commands became much more reliable.

### Current status

This was a major improvement, but not the final solution.

The assistant now understands commands much better, but it still sometimes mixes response languages. For example:

- I ask in English and sometimes it replies in Polish
- I ask in Polish and sometimes it replies in English

So the recognition side is much better now, but the response language logic still needs more work.


## 034. Assistant was listening to the wrong audio device

### Problem

At one point the assistant stopped listening through the microphone and behaved as if it was waiting only for text input in the terminal.

### Real cause

The system was using the wrong input device.  
It was listening to `default` instead of the real USB microphone array.

### Investigation

I checked available devices and found that the real microphone was:

- `reSpeaker XVF3800 4-Mic Array: USB Audio (hw:2,0)`
- `device_index = 1`
- sample rate `16000`

I also tested the microphone directly and confirmed that it was receiving strong audio signal.

### Fix

I updated the configuration to use the correct microphone device directly instead of relying on `default`.

After that, the assistant started listening to the real reSpeaker microphone properly.


## 035. Fallback to text input happened because voice input initialisation failed

### Problem

The assistant sometimes fell back to text input mode instead of using the microphone.

### Real cause

This happened when the Whisper input initialisation failed.  
The failure was caused by configuration problems during setup, for example:

- wrong model path
- wrong input device settings
- VAD-related setup issues
- not using the correct microphone source

### Fix

I fixed the configuration step by step:

- correct model path
- correct microphone device
- correct sample rate
- simpler diagnostic configuration first
- then improved configuration after the microphone started working

This helped me bring the assistant back from text-only fallback to real voice input.


## 036. Speech recognition was too slow because too many transcription passes were used

### Problem

After improving recognition, the assistant became too slow.

It was checking:

- auto
- then English
- then Polish

for the same audio input.

This improved the chance of correct recognition, but it made the assistant feel too slow.

### Fix

I changed the logic so that the assistant now prefers:

- auto first
- Polish only if needed

This is better for my use case because English is usually recognised correctly by auto anyway, and the extra support is mostly needed for Polish.

### Result

This made the assistant faster while keeping much better bilingual recognition than before.


## 037. Auto transcription sometimes produced wrong English-looking phrases for Polish commands

### Problem

Sometimes the auto transcript returned strange English phrases for Polish speech.  
A good example was when a Polish question about time became something like:

`Which is an hour?`

This caused the assistant to keep the wrong auto transcript instead of checking Polish properly.

### Fix

I adjusted the scoring and transcript selection logic so that suspicious auto results are treated more carefully.

I also made the system more willing to check Polish when the auto transcript looks weak or unnatural for a short command.

### Result

This improved Polish command handling and reduced false acceptance of bad auto transcripts.


## 038. Timer, focus, and break logic were growing in the wrong place

### Problem

The assistant logic was starting to become too mixed inside bigger core files.

This would make the project harder to grow later.

### Fix

I separated the logic into dedicated modules:

- `handlers_timer.py`
- `handlers_focus.py`
- `handlers_break.py`

I also kept a compatibility wrapper for the older timers handler file so the project would not break during refactoring.

### Result

The architecture is cleaner, easier to read, and better prepared for future expansion.


## 039. Main command and follow-up flow needed redesign

### Problem

The assistant needed cleaner behaviour for:

- startup
- help
- self introduction
- timer duration follow-up
- exit and shutdown confirmation
- focus to break transition

### Fix

I redesigned the main flow so the assistant now behaves in a more structured way.

Examples of improvements:

- English-first startup
- clearer self introduction
- better help answers
- cleaner yes / no handling
- better timer / focus / break follow-ups
- better confirmation behaviour

### Result

The assistant now feels much more like a real product and less like a set of isolated test commands.


---

## 040. Assistant mixed Polish and English during normal conversation

### Symptom
The assistant sometimes answered in English after a Polish question, even when the recognised command was clearly meant to be Polish.

Examples included:
- Polish help queries answered in English
- Polish memory replies answered in English
- Polish reminder creation confirmed in English

### Cause
The language routing was too loose.

The assistant could fall back to:
- previous conversation language
- ambiguous short transcript logic
- English default behaviour after uncertain recognition

This made the reply language less stable than I wanted.

### Fix
I rebuilt the language routing logic so that:
- the current command language is decided more strictly
- short Polish command patterns have stronger weight
- confirmation context keeps its own language
- the assistant commits language after command handling, not too early

### Result
Language behaviour became more stable and more predictable, especially for common Polish commands.

---

## 041. Short Polish commands were often replaced by English auto-transcripts

### Symptom
The assistant sometimes understood the meaning of a Polish command, but the transcript selected by the speech layer was English.

Examples included:
- Polish memory commands turned into English memory phrases
- Polish reminder commands turned into English reminder phrases
- Polish identity questions turned into English-style wording

### Cause
Whisper `auto` mode worked well overall, but for short commands it sometimes produced an English transcript that looked more confident than the real Polish input.

### Fix
I updated the Whisper selection layer so that:
- short commands are rechecked with forced Polish transcription
- exact Polish command phrases get stronger priority
- short Polish command token sets receive a stronger score
- Polish is preferred when the transcript clearly looks like a short Polish command

### Result
Short Polish commands became much more reliable.

---

## 042. Assistant reacted to keyboard typing, claps, and chair movement

### Symptom
The assistant sometimes reacted to non-speech sounds and described them as:
- typing
- clapping
- chair movement
- similar noise descriptions

This was not the behaviour I wanted. I wanted the assistant to ignore these sounds completely.

### Cause
Some noise events were still reaching the transcript stage and were being treated as low-confidence user input.

### Fix
I strengthened non-speech filtering in two places:
- the microphone capture and speech gating layer
- the main command loop transcript gate

I explicitly filtered common non-speech descriptions such as:
- `typing`
- `keyboard`
- `clapping`
- `chair movement`
- `stukanie`
- `klaskanie`
- `krzeslo`

### Result
The assistant became much quieter around non-speech noise and was less likely to reply when no real speech was present.

---

## 043. The assistant still asked whether time/date should be shown on screen

### Symptom
After a simple spoken query such as asking for the time, the assistant could still ask an extra follow-up about showing the result on the display.

This interrupted the conversation and made the interaction feel less natural.

### Cause
Older display-offer logic was still present in the response path.

### Fix
I removed the old screen-offer flow from the main interaction model and changed the rule to:

- normal question -> speak only
- explicit `show / pokaż / display` command -> speak and show

I also updated the response helpers so the old OLED offer behaviour would not return accidentally.

### Result
The interaction became simpler and closer to the premium behaviour I wanted.

---

## 044. Memory stored broken fragments after cut speech input

### Symptom
When speech was cut early, the assistant could save incomplete memory values.

Example:
- `klucze -> w`

### Cause
The earlier memory flow trusted partial parser output too easily.

### Fix
I added memory validation so that:
- very short fragments are rejected
- weak one-word endings are rejected
- suspicious incomplete values are not saved
- the assistant asks me to say the sentence again more clearly

I also cleared old bad entries from `memory.json`.

### Result
Memory became safer and cleaner.

---

## 045. Polish memory and reminder commands were not reliable enough

### Symptom
Some natural Polish commands were still unstable, especially:
- `usuń klucze z pamięci`
- reminder requests in Polish
- some memory recall flows

### Cause
The parser handled some English forms well, but several natural Polish sentence patterns needed better support.

### Fix
I updated the intent parser and follow-up logic so that:
- `usuń X z pamięci` is recognised
- Polish reminder phrasing is handled more naturally
- follow-up confirmations stay in the correct language
- reminder entries store the language used when they were created

### Result
Memory deletion and reminder handling became more consistent.

---

## 046. Assistant identity response did not match the intended behaviour

### Symptom
When I asked for the assistant name, it sometimes gave the full identity answer instead of only saying its name.

### Cause
The introduction flow did not distinguish clearly enough between:
- asking only for the name
- asking what or who the assistant is

### Fix
I changed the introduction logic so that:
- `What is your name?` / `Jak się nazywasz?` returns only the name
- `Who are you?` / `Kim jesteś?` / `Czym jesteś?` returns the fuller description

### Result
The assistant identity flow now matches the intended behaviour much better.

---

## 047. NeXa name pronunciation sounded wrong in speech output

### Symptom
The assistant name `NeXa` was pronounced incorrectly by TTS and sounded closer to `Nexar` than `Neksa`.

### Cause
Mixed-case branding text is not always pronounced well by local TTS engines.

### Fix
I applied pronunciation control in the voice output path and also replaced the spoken form in identity responses with a more phonetic version.

I also refreshed the TTS cache path so old cached audio would not keep replaying the wrong pronunciation.

### Result
The name pronunciation became easier to control and much closer to the intended spoken form.

---

## 048. Dialogue layer could crash because helper methods were missing

**Date:** 2026-04-03  
**Area:** dialogue / runtime stability  
**Status:** resolved  

### Problem
The conversation layer could fail during some conversational routes.

### Symptom
Some dialogue paths could trigger a runtime crash instead of returning a reply.

### Root cause
`companion_dialogue.py` was calling helper methods such as `_reply`, `_next_humour`, `_next_riddle`, and `_next_fact`, but those helper methods were not actually implemented in the file.

### Fix applied
The dialogue module was rebuilt so that:
- all required helper methods were implemented
- reply creation became more consistent
- display lines were generated safely
- deterministic humour, riddle, and fact replies worked again

### Result
The dialogue layer stopped crashing and became safe enough for further stabilisation work.

---

## 049. Assistant shutdown and system shutdown were too easy to confuse

**Date:** 2026-04-03  
**Area:** intent routing / safety  
**Status:** resolved  

### Problem
The assistant could blur the difference between:
- closing NeXa
- shutting down the Raspberry Pi system

### Symptom
Phrases like:
- `turn off NeXa`
- `turn off assistant`
- `turn off system`
- `wyłącz NeXa`
- `wyłącz asystenta`
- `wyłącz system`

could become mixed across the normalizer, semantic matcher, and parser layers.

### Root cause
The routing stack had multiple places that tried to help with shutdown understanding, but not all of them preserved the same distinction between assistant-level exit and full system shutdown.

### Fix applied
I hardened the whole shutdown path:
- the utterance normalizer stopped blurring assistant and system shutdown
- semantic intent matching became more conservative
- `assistant.py` was updated to map semantic shutdown hints into parser-safe commands
- the intent parser was expanded so it could understand the critical shutdown phrases directly

### Result
Assistant exit and system shutdown are now separated much more safely and predictably.

---

## 050. Time and date queries still used old follow-up behaviour

**Date:** 2026-04-03  
**Area:** temporal UX  
**Status:** resolved  

### Problem
Simple time or date questions could still behave like older follow-up flows instead of using the intended direct behaviour.

### Symptom
The assistant could act too indirectly around:
- time
- date
- day
- year

This made the interaction less natural.

### Root cause
The temporal handling flow still carried older behaviour patterns from before the newer premium interaction model.

### Fix applied
`handlers_time.py` was simplified so that:
- `ask_*` actions speak directly without extra follow-up noise
- `show_*` actions speak and also show the result on the display
- old pending follow-up state is cleared when a temporal action runs
- temporal replies are stored in short-term conversation memory

### Result
Time-related interactions became cleaner, faster, and more premium.

---

## 051. Runtime backend status could look healthier than it really was

**Date:** 2026-04-03  
**Area:** runtime diagnostics  
**Status:** resolved  

### Problem
The runtime could report that backends were ready even when some parts were actually degraded or using fallback behaviour.

### Symptom
Startup status could look too positive even if:
- voice input dependencies were missing
- Piper was not fully ready
- the runtime had already fallen back to text input or silent output

### Root cause
Backend readiness was being judged too optimistically at construction time.

### Fix applied
`runtime_builder.py` was redesigned so that it now:
- checks critical voice input dependencies more honestly
- checks Piper readiness more realistically
- reports degraded states instead of pretending everything is fully ready
- falls back more explicitly when required

### Result
The startup diagnostics now better match the real runtime state.

---

## 052. Response streaming felt slower than it needed to feel

**Date:** 2026-04-03  
**Area:** response UX / streaming  
**Status:** resolved  

### Problem
The assistant could feel slower than necessary even when the total reply was not very long.

### Symptom
Short acknowledgement phrases such as:
- `Jasne.`
- `Of course.`

did not always improve perceived responsiveness because chunk handling was not tuned well enough.

### Root cause
The response streamer merged or displayed chunks in a way that sometimes reduced the benefit of quick acknowledgement-first behaviour.

### Fix applied
`response_streamer.py` was improved so that:
- short acknowledgement chunks are preserved as separate quick reactions
- OLED summary prefers more useful content-like chunks
- pauses between chunk types are more deliberate
- the overall response feels less “stuck” before the main content

### Result
The assistant now feels faster and more natural even without full token-level model streaming.

---

## 053. Local LLM output still included technical runtime noise

**Date:** 2026-04-03  
**Area:** local LLM / output cleanup  
**Status:** resolved  

### Problem
Optional local LLM replies were at risk of including technical llama runtime noise.

### Symptom
Model output could contain unwanted fragments such as:
- build info
- model info
- prompt evaluation logs
- command help text
- other runtime leftovers

### Root cause
Raw llama output needed stronger filtering and stricter generation control.

### Fix applied
`local_llm.py` was improved so that:
- generation profiles are shorter and more predictable
- support replies stay brief
- knowledge replies get a controlled amount of space
- technical runtime lines are cleaned much more aggressively
- bad metadata-like output is rejected instead of spoken

### Result
Optional local LLM replies became safer and more product-like.

---

## 054. Semantic intent matching needed stronger safety and better examples

**Date:** 2026-04-03  
**Area:** semantic routing  
**Status:** resolved  

### Problem
The semantic matcher needed better examples and safer thresholds for real use.

### Symptom
Without hardening, the semantic layer could be too weak in some areas and too risky in others.

### Root cause
The matcher needed:
- better support examples
- better humour and riddle coverage
- safer shutdown distinction
- cleaner follow-up choice handling

### Fix applied
`semantic_intent_matcher.py` was expanded and rebalanced so that:
- support / tired signals are stronger
- talk requests are recognised better
- humour and riddle examples are clearer
- break / focus / decline follow-up choices are more reliable
- shutdown intent is handled with stronger safety checks

### Result
The semantic layer became more useful without becoming unsafe.

---

## 055. Critical commands still depended too much on the semantic layer

**Date:** 2026-04-03  
**Area:** parser hardening  
**Status:** resolved  

### Problem
Some critical commands were understood mainly because the semantic layer helped them.

### Symptom
Commands like:
- `turn off NeXa`
- `turn off assistant`
- `turn off system`
- `wyłącz NeXa`
- `wyłącz asystenta`
- `wyłącz system`

worked, but the parser itself was still not strong enough on its own.

### Root cause
The parser had not yet fully absorbed the key assistant/system shutdown distinctions.

### Fix applied
`intent_parser.py` was hardened so that it now directly understands critical shutdown and exit phrases without needing to rely too heavily on semantic rescue.

### Result
The core command path became safer and more production-minded.

---

## 056. Follow-up continuity was too weak for a companion-style assistant

**Date:** 2026-04-03  
**Area:** follow-up flow / continuity  
**Status:** resolved  

### Problem
The assistant could complete a follow-up correctly, but the conversation continuity still felt weaker than intended.

### Symptom
This affected:
- yes / no flows
- mixed suggestion offers
- exit / shutdown confirmation
- name capture
- timer duration follow-ups
- memory and reminder confirmation flows

### Root cause
Follow-up replies were not consistently being treated as part of the recent conversation context.

### Fix applied
`followups.py` was rebuilt so that:
- follow-up replies are stored in short-term conversation memory
- decline / repeat / confirmation behaviour is more consistent
- mixed action offers are more natural
- interruption by a new command is handled more safely

### Result
Follow-up interaction became more coherent and more companion-like.

---

## 057. Action handlers were not consistently feeding conversation continuity

**Date:** 2026-04-03  
**Area:** continuity / core handlers  
**Status:** resolved  

### Problem
Several direct action handlers worked correctly, but their replies were not always written into short-term conversation memory.

### Symptom
This meant NeXa could execute actions well, but still have weaker awareness of what it had just said.

### Root cause
Older action handlers were focused on execution and output, but not yet fully integrated into the newer short-term conversation continuity layer.

### Fix applied
I updated the following handler groups so their spoken replies are also stored in recent conversation memory:
- system
- memory
- reminders
- timer
- focus
- break

### Result
The assistant now has stronger continuity after practical actions, not only after conversation replies.

---

## 058. Conversation memory needed cleanup after continuity improvements

**Date:** 2026-04-03  
**Area:** conversation memory  
**Status:** resolved  

### Problem
After more assistant replies started being stored in memory, the short-term memory itself needed tightening.

### Symptom
The context block used for recent conversation risked becoming:
- too repetitive
- too noisy
- less useful for the local dialogue and LLM layers

### Root cause
The system had gained more continuity, but the memory service still needed stronger trimming and duplicate control.

### Fix applied
`conversation_memory.py` was improved so that it now:
- rejects consecutive duplicates
- trims long turns more safely
- keeps context lightweight
- skips low-value startup or retry noise
- builds cleaner recent context blocks

### Result
Conversation continuity improved without making context quality worse.

---

## 059. Language routing still slipped on short follow-up answers

**Date:** 2026-04-03  
**Area:** bilingual routing  
**Status:** resolved  

### Problem
Very short follow-up phrases could still push the assistant toward the wrong language.

### Symptom
This affected cases such as:
- `yes / no`
- `tak / nie`
- short timer values such as `5 minutes`
- short Polish values such as `2 minuty`

### Root cause
Short utterances do not carry much language information on their own, so they need stronger context-aware handling.

### Fix applied
`language.py` was rebuilt so that:
- confirmation context has stronger language control
- short duration answers keep the follow-up language
- bilingual scoring is more stable
- short English and Polish command cues are weighted better

### Result
Reply language became much more stable during short follow-up interactions.

---

## 060. Runtime documentation and example settings drifted away from the real project state

**Date:** 2026-04-03  
**Area:** documentation / configuration  
**Status:** resolved  

### Problem
The repo documentation no longer matched the real runtime direction of NeXa.

### Symptom
Example settings and docs still reflected older stages of the project, including outdated engine assumptions and older architecture descriptions.

### Root cause
The runtime had evolved faster than the supporting documentation.

### Fix applied
I updated:
- `config/settings.example.json`
- `README.md`
- `docs/architecture_notes.md`

so they now reflect:
- `faster-whisper`
- `silero-vad`
- `Piper`
- response streaming
- semantic routing
- runtime builder
- short-term conversation memory
- optional local LLM path

### Result
The project now has a clearer technical source of truth for development, reporting, and viva discussion.

---

## 061. Assistant started normally but did not hear real speech

**Date:** 2026-04-03  
**Area:** audio input / STT frontend  
**Status:** resolved  

### Problem
The assistant started successfully, displayed a healthy startup state, and entered the listening loop, but it did not respond to real speech.

### Symptom
The terminal repeatedly showed:
- `No speech recognized`

while the rest of the system looked healthy.

### Root cause
The runtime was listening to the wrong audio source because the input device was still effectively using the default system path rather than the intended microphone array.

### What I checked
I verified the available capture devices and found that the correct microphone was:
- `reSpeaker XVF3800 4-Mic Array`

### Fix applied
The voice input configuration was updated so that the runtime explicitly targets the `reSpeaker` microphone instead of depending on the default input device.

### Result
The assistant started listening to the real microphone again.

---

## 062. Speech onset was too strict for the real microphone setup

**Date:** 2026-04-03  
**Area:** VAD / speech onset tuning  
**Status:** resolved  

### Problem
Even after the microphone path was mostly correct, speech detection was still too strict for the real voice input conditions.

### Symptom
The assistant could behave as if no one was speaking, especially before the microphone and VAD settings were tuned for the actual device.

### Root cause
The front-end voice activity detection settings were too strict for the real reSpeaker input path and room conditions.

### Fix applied
The voice input settings were tuned by:
- enabling explicit microphone targeting through `device_name_contains`
- turning on debug mode for diagnosis
- lowering the VAD threshold
- slightly relaxing speech start and silence settings
- adjusting block and pre-roll behaviour

### Result
After these settings were updated, the assistant started hearing speech correctly again and the voice loop became usable in practice.


## 063. I moved the project from microSD to SSD and rebuilt the runtime from scratch


### Problem
I did not want to continue building the assistant on top of the earlier microSD-based setup because I wanted a cleaner and more stable base.

### Symptom
The project had already gone through many runtime changes, package changes, and audio-stack changes, so I wanted a cleaner rebuild point before pushing the assistant further toward a premium state.

### Root cause
The earlier setup was no longer the best base for the current stage of the project.

### Fix applied
I:
- moved the working setup to SSD
- installed the system again
- updated the system packages
- installed the required project dependencies again
- rebuilt the assistant environment on the new setup

### Result
The project now runs from a cleaner and stronger base, which is better for further premium runtime work.

---

## 064. FasterWhisper input failed because of a bad import change
 

### Problem
The FasterWhisper voice input backend stopped working after an edit in the input module.

### Symptom
The assistant fell back to text input and no longer used the real microphone path.

### Root cause
A wrong import was present in the file:
- `import times`

instead of:
- `import time`

That stopped the voice input backend from loading correctly.

### Fix applied
I corrected the import and restarted the runtime.

### Result
The real voice input path started working again instead of falling back to text mode.

---

## 065. The main loop became inconsistent with different voice input backend interfaces
 

### Problem
The main runtime loop expected methods that were not always exposed consistently by the active voice backend.

### Symptom
The assistant could fail with attribute errors during wake handling or command listening.

### Root cause
The voice loop and the voice input backend were temporarily out of sync while the wake architecture was being changed.

### Fix applied
I rebuilt the public listening methods more carefully and made the runtime use a cleaner and more stable interface again.

### Result
The main loop stopped failing because of missing listening methods.

---

## 066. Standby wake flow still depended too much on transcription-first behaviour
 

### Problem
The assistant still relied too much on short speech transcription during standby.

### Symptom
Wake detection worked only as a partial step and still carried too much delay for a premium assistant feel.

### Root cause
The standby layer was still too close to a full STT path instead of a dedicated wake detector.

### Fix applied
I used that approach only as a temporary bridge and then moved the project toward a dedicated wake-word architecture.

### Result
The project was able to move away from transcription-first standby toward a real wake-gate design.

---

## 067. Training the custom wake-word model in Colab became messy because of dependency drift


### Problem
The custom wake-word model training workflow did not run cleanly in Colab.

### Symptom
I ran into multiple environment and dependency errors, including:
- CUDA-related mismatch problems
- missing training modules
- broken imports
- notebook steps that no longer matched the current package layout

### Root cause
The notebook and supporting packages had dependency drift and parts of the example workflow no longer matched the current environment exactly.

### Fix applied
I rebuilt the Colab workflow step by step:
- fixed the PyTorch CPU setup
- re-cloned the required repos
- repaired generator imports
- added compatibility wrappers
- installed missing training dependencies one by one

### Result
The custom wake-word training workflow finally ran far enough to generate clips, compute features, train the model, and export the ONNX file.

---

## 068. The wake-word training pipeline failed because required training data was missing


### Problem
The training pipeline could not continue because required training assets were missing.

### Symptom
The workflow failed on missing resources such as:
- `mit_rirs`
- background audio folders
- validation feature files

### Root cause
The full training pipeline expected more data than the simple audio test stage.

### Fix applied
I downloaded and prepared the required assets:
- room impulse response data
- background audio data
- feature data files used by the training config

### Result
The pipeline could continue beyond the setup stage and start generating real training features.

---

## 069. Augmentation failed because the generated clips did not have the correct sample rate


### Problem
The augmentation stage failed because the generated positive clips were not all in the sample rate expected by the training pipeline.

### Symptom
The training step failed with:
- `Error! Clip does not have the correct sample rate!`

### Root cause
The generated clips were not all consistently stored at 16 kHz.

### Fix applied
I checked the generated `.wav` files, found the incorrect sample rates, and resampled the clips to 16 kHz before rerunning augmentation.

### Result
The feature generation stage completed successfully.

---

## 070. The training cache became incomplete and blocked the next stage
 

### Problem
The training process could sometimes see partial output and assume the feature stage was already complete.

### Symptom
One stage reported that features already existed, but the next stage still failed because expected files were missing.

### Root cause
The output cache for the custom model was incomplete.

### Fix applied
I cleared the broken output directory and rebuilt the training stages in the correct order:
- generate clips
- augment clips
- train model

### Result
The training flow became consistent again.

---

## 071. ONNX export failed because the ONNX package was missing


### Problem
The wake-word model trained successfully, but export failed at the final ONNX stage.

### Symptom
The training ended with an export error instead of producing the final model file.

### Root cause
The `onnx` package was not installed in the Colab environment.

### Fix applied
I installed the missing ONNX package and reran the final training/export stage.

### Result
The ONNX wake-word model was produced successfully.

---

## 072. TFLite export failed, but the ONNX wake model was already enough for the project


### Problem
After the ONNX model was saved, the workflow still failed during TFLite export.

### Symptom
The training run ended with a conversion error after saving:
- `nexa.onnx`

### Root cause
The TFLite conversion path depended on extra tooling that was not required for my current Raspberry Pi use case.

### Fix applied
I stopped treating the TFLite failure as a blocker because the ONNX model I needed had already been created successfully.

### Result
I kept the generated `nexa.onnx` model and used that as the real wake-word model for the project.

---

## 073. The dedicated wake gate did not start because the custom model file was missing on the Raspberry Pi


### Problem
The dedicated wake gate could not start on the Raspberry Pi.

### Symptom
The assistant started with:
- `Wake gate fallback active: FasterWhisper`

instead of using the dedicated wake detector.

### Root cause
The trained model file:
- `models/wake/nexa.onnx`

was not yet present in the project on the Raspberry Pi.

### Fix applied
I copied the trained ONNX model into:
- `models/wake/nexa.onnx`

and tested the wake gate again.

### Result
The project was able to load the dedicated wake model locally.

---

## 074. Newer openWakeWord install failed on Raspberry Pi because of Linux dependency issues
 

### Problem
I tried to move to a newer `openwakeword` version on the Raspberry Pi, but installation failed.

### Symptom
The install failed because of missing Linux dependency packages during pip resolution.

### Root cause
The newer package line pulled Linux-specific dependencies that were not available cleanly in the current Raspberry Pi environment.

### Fix applied
I stopped pushing the upgrade and pinned the project back to:
- `openwakeword==0.4.0`

so I could get a stable local wake gate running first.

### Result
This gave me a practical and stable base for the dedicated wake-word gate.

---

## 075. The dedicated wake gate loaded but did not react because of API and score parsing mismatch
 

### Problem
The dedicated wake gate loaded successfully, but it still did not react to the wake word.

### Symptom
The assistant started with:
- `Dedicated wake gate active: openWakeWord`

but the debug output stayed around:
- `OpenWakeWord score=0.000`

### Root cause
The older `openwakeword` runtime API did not match the newer assumptions used in the wake gate code, so the model output was not being read correctly.

### Fix applied
I:
- adapted the wake gate to the older `openwakeword` API
- added compatibility handling for model construction
- adjusted result parsing so the score could be read properly
- tuned threshold and trigger settings for testing

### Result
The dedicated local wake gate finally started reacting to the custom `NeXa` wake-word model in real runtime use.

---

## 076. The project reached the first real dedicated local wake-word milestone
 

### Problem
The project still needed to prove that the assistant could wake locally through a dedicated model instead of only through transcription-based fallback logic.

### Symptom
Earlier wake behaviour was still too dependent on the heavier fallback path.

### Root cause
The dedicated wake-word pipeline was not fully trained, exported, deployed, and integrated yet.

### Fix applied
I completed the full chain:
- trained a custom wake-word model for `NeXa`
- exported `nexa.onnx`
- copied it into the Raspberry Pi project
- integrated it into the dedicated wake gate
- verified that the assistant could react through the local wake path

### Result
This became the first real milestone where NeXa used a dedicated local wake-word path instead of depending only on the earlier transcription-based wake fallback.


---

## 077. The assistant could hear its own voice after speaking


### Problem
After some spoken outputs, the assistant could still react to its own voice.

### Symptom
This could happen after:
- timer finished
- reminder speech
- normal spoken replies
- follow-up prompts

In practice, this created the risk of self-triggered behaviour or strange extra listening after NeXa had just spoken.

### Root cause
Playback, wake detection, and full STT were working, but they were not coordinated strongly enough as one audio lifecycle.

The system needed a shared rule for when user input should be blocked because the assistant was still speaking or had just finished speaking.

### Fix applied
I added a dedicated audio coordination layer.

This layer now:
- tracks when assistant playback starts
- tracks when assistant playback ends
- keeps a short post-speech shield
- lets wake detection and STT check whether input should stay blocked

I connected this coordination layer to:
- voice output
- FasterWhisper input
- the dedicated wake gate
- the main runtime loop

### Result
The assistant became much more stable after speaking and was less likely to react to her own TTS.

---

## 078. Async speech could leave the assistant in the wrong conversational state


### Problem
Background events could leave the assistant behaving as if a live conversation was still open.

### Symptom
This affected cases such as:
- timer finished
- reminder due
- break finished
- focus finished

After speaking one of these messages, the assistant could still behave too much like it was waiting for a follow-up.

### Root cause
Async notifications were not being treated differently enough from normal user-led conversation turns.

### Fix applied
I introduced a dedicated async notification delivery path.

This path now:
- clears old pending conversation context
- delivers the spoken notification
- closes the active window
- returns the assistant to standby

I also removed the old post-focus break offer behaviour from the async finish path because it kept the assistant too sticky.

### Result
Async speech now behaves more like a clean notification and less like an unfinished conversation.

---

## 079. Fast commands were still travelling through heavier conversation flow


### Problem
Simple direct commands were still relying too much on the heavier routing path.

### Symptom
This affected commands such as:
- time
- day
- month
- year
- timer
- focus
- break
- memory actions
- reminders
- assistant identity
- exit and shutdown

Even when the command was simple, the path was heavier than I wanted for a premium feel.

### Root cause
The system still depended too much on one general route instead of splitting direct commands away from dialogue-style behaviour.

### Fix applied
I added a separate fast command lane.

This lane now handles clear direct actions with a lighter deterministic path.

I also used it to make sure that:
- a new clear command can override an older follow-up
- temporal replies behave directly
- simple actions feel faster and cleaner

I also added missing month support to the temporal command set.

### Result
Simple commands became faster, cleaner, and more predictable.

---

## 080. `responses.py` failed after the month update because of a copy-paste indentation mistake



### Problem
The assistant failed to start after I added month support.

### Symptom
Python raised:
- `IndentationError: expected an indented block`

### Root cause
While updating `responses.py`, part of the new month payload function was pasted with the wrong indentation.

### Fix applied
I replaced the broken part with a clean full-file version of `responses.py` so the temporal response helpers were correctly structured again.

### Result
The assistant started normally again and month-related responses worked.

---

## 081. Slower dialogue replies needed a natural acknowledgement instead of dead silence


### Problem
When a slower reply path needed more time, the assistant could stay silent for too long.

### Symptom
This made some conversation-style replies feel uncertain or less polished, even when the final answer was correct.

### Root cause
The system did not yet have a delayed acknowledgement layer for slower dialogue work.

### Fix applied
I added a thinking acknowledgement service.

This service can now wait briefly and then speak a short natural phrase such as:
- `Just a moment.`
- `Give me a second.`
- `I’m checking.`
- `Let me think.`

I only connected this to slower dialogue paths, not to the fast command lane.

### Result
The assistant now feels more responsive during slower reply generation without making simple commands feel artificially delayed.

---

## 082. Wake-word interruption support needed a safer first version

**Date:** 2026-04-07  
**Area:** interruptibility / voice control  
**Status:** partial  

### Problem
I wanted the assistant to be easier to interrupt while speaking or thinking.

### Symptom
Without a safer interrupt layer, the old flow could feel too rigid once speech output had already started.

### Root cause
Full open interruption is harder in a local speaker-and-microphone setup because I also need to protect the system from self-hearing.

### Fix applied
I started with a safer interrupt model based on the wake path.

This version allows me to:
- use the wake path again while the assistant is speaking or thinking
- interrupt the current output
- reopen the listening window
- then give a cancel request or a new command

I also added the first interrupt control layer and connected it to playback handling.

### Result
Interruption is now possible in a safer and more controlled way, but this part still needs more refinement before I treat it as final premium barge-in behaviour.


## 083. Wake gate looked healthy in code but still degraded at startup

**Date:** 2026-04-08  
**Area:** wake runtime / startup status  
**Status:** resolved  

### Problem
The assistant started, but the runtime still reported that the wake gate was degraded.

### Symptom
Startup looked mostly correct, but the assistant reported that the wake module was not fully healthy.

### Root cause
The wake path could fail during runtime construction and fall back in a way that did not behave like a real working standby wake layer.

### Fix applied
I rebuilt the wake fallback path so the runtime no longer depended on a dead standby fallback.  
Instead of leaving wake handling in a no-op state, I connected a compatibility wake path through the real voice input backend.

### Result
The runtime could still start honestly, but wake handling no longer got stuck in a useless fallback state.

---

## 084. Two different input owners were fighting for the microphone

**Date:** 2026-04-08  
**Area:** audio architecture / microphone ownership  
**Status:** improved  

### Problem
The wake gate and the speech input backend were both trying to own microphone capture.

### Symptom
This created unstable behaviour during standby and wake transitions.  
In the broken state it could also lead to audio device errors and unreliable wake behaviour.

### Root cause
The project still had two separate input owners:
- wake capture
- full STT capture

That architecture was too fragile for the current Raspberry Pi runtime.

### Fix applied
I changed the runtime direction toward a single-capture flow.

The important changes were:
- standby wake fallback through the same voice input backend
- cleaner handoff rules between standby and active listening
- removal of the old behaviour where separate parts competed for the same microphone path

### Result
The voice loop became much more stable and much easier to control.

---

## 085. Wake settings were too aggressive and made the standby loop unstable

**Date:** 2026-04-08  
**Area:** wake config / standby stability  
**Status:** resolved  

### Problem
The wake configuration was too aggressive for real runtime use.

### Symptom
The assistant could become unstable in standby and the logs showed that several wake settings had to be corrected upward at runtime.

### Root cause
The wake thresholds, trigger level, cooldown values, and related settings were too optimistic for the real microphone and room conditions.

### Fix applied
I cleaned the runtime settings and replaced the earlier aggressive wake values with calmer and safer ones.

I also turned off wake debug spam and reduced overly noisy runtime behaviour.

### Result
The standby loop became calmer and more realistic.

---

## 086. Debug-heavy wake behaviour increased noise in the runtime loop

**Date:** 2026-04-08  
**Area:** wake diagnostics / runtime stability  
**Status:** resolved  

### Problem
The wake loop was producing too much debug output during normal runtime.

### Symptom
The terminal was filled with repeated wake score logs and this made troubleshooting noisy and the runtime less clean.

### Root cause
Wake debugging was still enabled in a configuration that should already have been treated as normal runtime, not heavy diagnosis mode.

### Fix applied
I disabled the noisy wake debug path and kept the runtime closer to a clean user-facing behaviour.

### Result
The wake loop became much quieter and easier to evaluate.

---

## 087. Compatibility wake did not react because short wake phrases were rejected like weak commands

**Date:** 2026-04-08  
**Area:** wake logic / STT compatibility mode  
**Status:** resolved  

### Problem
After moving toward single-capture mode, the assistant still did not react to `NeXa`.

### Symptom
The assistant looked healthy and entered standby, but it ignored repeated attempts to wake it.

### Root cause
The compatibility wake path reused the normal STT backend, but that backend was still judging short wake phrases too strictly.  
A short wake phrase such as `NeXa` was being filtered like a weak or incomplete command instead of being treated as a valid wake event.

### Fix applied
I added a dedicated `listen_for_wake_phrase()` path to the FasterWhisper input backend.

This wake-specific path:
- accepts short wake-style speech more easily
- uses a lighter wake-oriented capture flow
- avoids treating the wake word like a normal full command

### Result
The assistant finally started reacting to the wake word through the shared input path.

---

## 088. Single-capture mode still broke standby because the shared voice input was being closed too often

**Date:** 2026-04-08  
**Area:** main loop / single-capture flow  
**Status:** resolved  

### Problem
Even after moving toward one shared input owner, standby still behaved incorrectly.

### Symptom
The assistant could enter standby but fail to react properly because the shared voice input path was being closed and reopened in the wrong places.

### Root cause
The main loop still treated the wake path and the command path as if they were fully separate, even when both were using the same voice input backend.

### Fix applied
I adjusted the main loop so it no longer closes the shared voice input path during standby when compatibility wake is active.

### Result
The single-capture path became stable enough to work in practice.

---

## 089. Wake response was working, but it was still far too slow for a premium experience

**Date:** 2026-04-08  
**Area:** wake performance / response speed  
**Status:** resolved  

### Problem
The assistant could wake, but sometimes only after a very long delay.

### Symptom
I could say `NeXa` many times and the assistant would react much later than expected.

### Root cause
The wake compatibility path was still too heavy.  
It was doing too much work for a very short wake phrase and the wake-specific speech path still behaved too much like a normal command transcription path.

### Fix applied
I reduced the wake path cost by:
- warming up the speech runtime earlier
- shortening the wake capture window
- shortening wake silence handling
- avoiding unnecessary multi-pass wake processing
- making the wake path much lighter than the full command path

### Result
Wake response became much faster and much closer to the behaviour I wanted.

---

## 090. The assistant started catching wake correctly, but post-reply listening still needs more polish

**Date:** 2026-04-08  
**Area:** active listening / post-reply interaction  
**Status:** open  

### Problem
After wake and successful command handling, the assistant could still catch weak or unwanted phrases during the follow-up or grace window.

### Symptom
The runtime worked much better overall, but some unclear transcriptions could still appear after valid replies.

### Root cause
The wake path is now much better, but the post-reply interaction window still needs more tuning so that it feels cleaner and more premium.

### Fix applied
No final fix yet.

### Current result
The core voice loop is much better now:
- wake works
- command handling works
- shutdown flow works
- speed is much better

But the grace and follow-up listening windows still need more polishing.

### Follow-up
Next improvement area:
- tighten grace window behaviour
- reduce weak post-reply transcriptions
- improve confirmation handling even more


## 091. Hailo backend installation and startup path were harder than expected
 

### Problem
The move toward the AI HAT+ 2 and Hailo-backed local LLM path was not a simple plug-and-play change.

### Symptom
The assistant could be configured for the new backend direction, but the real runtime path was still fragile during installation and startup.

### Root cause
The Hailo direction introduced a new kind of dependency chain:
- accelerator-side setup
- backend serving setup
- runtime connection from the assistant
- health-check reliability
- startup order correctness

### Fix applied
I treated the Hailo path as a dedicated backend boundary instead of mixing it directly into assistant logic.

I also checked:
- installation readiness
- backend startup path
- whether the backend was reachable from the assistant runtime
- whether the runtime should report degraded or healthy status honestly

### Result
The project moved closer to a proper local accelerated LLM architecture, even though this area still required more stabilisation than a normal software-only change.

---

## 092. Main assistant runtime could not reliably connect to the Hailo-backed backend


### Problem
Even when the Hailo-related setup existed, the main assistant runtime did not always connect cleanly to the backend.

### Symptom
The assistant could look mostly healthy while richer local LLM behaviour was still unavailable or only partially available.

### Root cause
This was not only a model issue.  
The real problem was the runtime boundary between:
- the NeXa assistant process
- the dedicated local backend process

### Fix applied
I treated backend availability as a real runtime concern and checked:
- server reachability
- backend health path
- startup order
- whether degraded state was being reported honestly

### Result
The project gained a cleaner direction for backend-aware startup and diagnostics instead of pretending the LLM path was healthy when it was not.

---

## 093. Speaker path confusion made it look like the assistant was broken


### Problem
At one point the assistant could generate replies correctly, but the audible output path was still unreliable or confusing.

### Symptom
The system looked alive, but real spoken feedback was missing or inconsistent.

### Root cause
The output path had to be treated as multiple separate layers:
- reply generation
- speech synthesis
- playback command
- speaker routing

A problem in one of these layers could make the whole assistant look broken even when the rest of the runtime was still working.

### Fix applied
I checked the output path more carefully as a pipeline instead of treating it as one single TTS problem.

### Result
This made speaker-related failures much easier to diagnose and reduced confusion between “the assistant cannot answer” and “the assistant answered but audio playback failed”.

---

## 094. Runtime fell back to text input and behaved as if it wanted typed commands

**Date:** 2026-04-10  
**Area:** voice input / degraded fallback  
**Status:** improved  

### Problem
The assistant stopped behaving like a voice assistant and instead acted as if it wanted typed input.

### Symptom
It looked like the system was waiting for text instead of listening through the real microphone.

### Root cause
The real voice input path had failed or degraded, and the runtime had fallen back to a developer-style text input path.

### Fix applied
I treated this as a degraded runtime condition, not as normal assistant behaviour.

I also improved the runtime understanding of this failure mode so it would be easier to diagnose instead of looking like a normal working assistant.

### Result
The project now handles this problem more consciously and the runtime behaviour is easier to interpret when voice input is not really active.

---

## 095. Wake spam caused repeated unstable wake behaviour

**Date:** 2026-04-10  
**Area:** wake loop / input stability  
**Status:** improved  

### Problem
The assistant could enter a noisy repeated wake pattern instead of behaving like a calm premium standby system.

### Symptom
Wake handling could feel like:
- repeated wake attempts
- noisy wake logs
- unstable wake triggering
- repeated `wake`-style behaviour instead of one clean wake event

### Root cause
Wake stability depended on more than the wake model alone.

The real problem involved:
- microphone input quality
- short phrase handling
- threshold and cooldown tuning
- coordination with assistant playback
- post-reply listening behaviour

### Fix applied
I hardened the wake path and treated wake stability as a full runtime behaviour problem, not only as a model-threshold problem.

### Result
Wake handling became much more controlled, although this area still remained one of the most important premium-polish tasks.

---

## 096. Pan-tilt motion needed its own safer hardware test path
  

### Problem
After adding the moving platform, I needed a reliable way to test motion without mixing too much unrelated assistant logic into the hardware checks.

### Symptom
Without dedicated motion tests, it would be harder to separate:
- parsing problems
- runtime problems
- hardware movement problems
- calibration problems

### Root cause
The new platform added physical behaviour, so simple software-only checks were no longer enough.

### Fix applied
I added dedicated pan-tilt test paths so platform behaviour could be tested directly and more safely.

### Result
Motion hardware became easier to validate and safer to improve.

---

## 097. LCD and movement now needed coordinated behaviour instead of separate testing only


### Problem
After mounting the LCD on the moving platform, the project needed a better way to test visual output together with motion.

### Symptom
Separate testing of only display or only movement was no longer enough for the new hardware layout.

### Root cause
The project had moved into a more embodied assistant setup where:
- display
- movement
- expression timing

had to work together.

### Fix applied
I expanded the hardware test direction so combined behaviour scripts could control both motion and visual feedback.

### Result
This created a better basis for future premium expression testing.

---

## 098. Camera work moved forward, but the runtime vision path is still not fully finished


### Problem
Camera testing started moving forward, but the project still needed a clearer separation between hardware validation and fully productised vision runtime support.

### Symptom
Camera-related work existed at the testing and preparation level, but this did not yet mean the whole production vision path was complete.

### Root cause
Testing hardware readiness is not the same as delivering a fully integrated stable runtime service.

### Fix applied
I treated camera work in this stage as preparation, validation, and architecture progression rather than overstating it as fully finished production vision support.

### Result
The project is closer to the future camera stage, but this area still needs a full runtime integration pass.


---

## 099. STT benchmark contract stopped feeding the speech-finalized benchmark note
 

### Problem
A Stage 4 STT contract test failed even though the speech recognition service itself was returning a valid transcript.

### Symptom
The test:

- `tests/test_stage4_stt_contract.py`

failed with:

- expected benchmark note call count = `1`
- actual call count = `0`

This meant the transcript result was no longer reaching the benchmark speech-finalized contract path correctly.

### Root cause
The benchmark note handoff between the transcript result and the assistant-side benchmark service had drifted.  
The STT result was valid, but the helper path that should feed benchmark speech-finalized metadata was not hitting the expected assistant benchmark hook.

### Fix applied
The benchmark note contract path was restored so that:
- transcript text
- backend label
- mode
- speech-finalized benchmark note

all flow together again through the expected contract boundary.

### Result
The failing STT benchmark contract test passed again, and the transcript result correctly fed the benchmark speech-finalized flow.

---

## 100. Benchmark sample diagnostics misclassified voice turns as non-voice
  

### Problem
The turn benchmark diagnostics service was misclassifying valid voice turns.

### Symptom
The tests in:

- `tests/test_turn_benchmark_sample_diagnostics.py`

failed because `description["voice"]` was `False` even for samples with:

- `input_source = "voice"`

This affected both:
- skill turns
- LLM turns

### Root cause
The sample description logic was relying too heavily on secondary routing metadata instead of correctly recognizing direct voice-origin samples.

As a result:
- a voice + skill turn could be described incorrectly
- a voice + llm turn could also be described incorrectly

### Fix applied
The diagnostics service was corrected so that voice classification is derived properly from voice-origin benchmark fields, including the direct input source.

### Result
Voice turns are now diagnosed correctly and the benchmark inspection tools produce more trustworthy output.

---

## 101. Premium validation capture could look broken because the benchmark store was reset without a ready runtime


### Problem
The capture workflow could show repeated zero-sample output even when the user expected it to start collecting turns.

### Symptom
After running:

- `python scripts/run_premium_validation_capture.py --reset --stage llm_short`
- `python scripts/run_premium_validation_capture.py --stage llm_short --watch`

the tool kept showing:
- `total samples: 0`
- `window samples: 0`
- `benchmark file looks idle`

### Root cause
The benchmark store was being reset correctly, but the runtime was not actually in a valid capture-ready state yet.

Common reasons included:
- runtime stopped
- runtime failed
- runtime degraded
- no active turn processing
- the running assistant instance was not writing to the same benchmark file path

### Fix applied
The validation capture output and troubleshooting flow were treated more explicitly as a runtime-state-sensitive tool, not just a passive benchmark viewer.

### Result
It became clearer that:
- zero samples after reset does not automatically mean benchmark code is broken
- the first thing to verify is whether the runtime is really active and writing new turns

---

## 102. Runtime status and benchmark capture could drift apart and confuse troubleshooting


### Problem
Benchmark capture output and runtime status could tell different parts of the truth, which made debugging confusing.

### Symptom
Examples included:
- benchmark watcher showing no new samples
- `runtime_status.json` showing `stopped`, `failed`, `degraded`, or old timestamps
- active expectations not matching what the assistant was really doing

### Root cause
The project already had:
- runtime status
- benchmark traces
- systemd acceptance checks

but the operator still needed to interpret them together.

A stale or degraded runtime status could make benchmark capture look broken even when the benchmark code was technically fine.

### Fix applied
The troubleshooting flow shifted to reading the system as a coordinated set of signals:
- runtime status
- benchmark file age
- latest benchmark turn
- service state
- whether `main.py` was actually running

### Result
This made it much easier to separate:
- “capture is broken”
from
- “runtime is not actually ready”
from
- “runtime is active but not using the expected input path”

---

## 103. Premium validation failed because only skill turns were being collected

 

### Problem
The benchmark file could contain many valid completed turns and still fail premium validation because the sample mix was wrong.

### Symptom
The validation output showed cases such as:
- `skill` segment populated
- `voice` segment empty or incomplete
- `llm` segment empty or incomplete

This happened even though the benchmark file itself was valid and contained completed turns.

### Root cause
The assistant was executing real interactions, but the captured turns did not cover the required validation mix.

Examples:
- deterministic skills only
- too few true voice turns
- too few streamed LLM turns
- turns routed differently than expected

### Fix applied
The capture workflow was treated as scenario-driven validation rather than “just use the assistant for a bit”.

The user had to deliberately drive:
- short voice skill turns
- short streamed LLM turns

with the correct prompts and with the runtime actually active.

### Result
Benchmark failure became easier to understand:
- not every failure means broken code
- sometimes the validation window simply does not contain the right kinds of turns yet

---

## 104. The first visible bottleneck was not LLM first-chunk latency, but the earlier voice path

 
### Problem
At first glance it looked like the local LLM path might still be the main premium blocker.

### Symptom
Premium validation still failed, so it was tempting to assume the local LLM backend was still too slow.

### Root cause
Once the segmented benchmarks were inspected properly, the numbers showed a different reality.

The real pattern was:
- `llm_first_chunk_ms` could already pass
- `response_first_audio_ms` for LLM could also pass or be close
- but the earlier voice path was still too expensive

The biggest bottlenecks were:
- wake latency
- STT latency
- route-to-first-audio before or around skill / conversation handoff

### Fix applied
The troubleshooting focus moved away from blaming the LLM by default and toward:
- wake path
- STT path
- route timing
- skill path end-to-end latency
- capture mode and wake mode correctness

### Result
This was an important direction correction.
The project stopped optimising the wrong layer first.

---

## 105. The benchmark tools needed to be read as product observability, not only as pass/fail scripts
 

### Problem
It was possible to treat the benchmark and premium validation scripts as simple pass/fail tools, which hid useful product-level information.

### Symptom
The same run could contain valuable clues, for example:
- runtime not ready
- benchmark file idle
- wrong segment population
- route classification mismatch
- capture writing to the wrong place
- degraded voice mode
- LLM actually passing key first-response metrics

but these clues were easy to miss if the user looked only at the final `FAIL`.

### Root cause
The tools were doing more than one job:
- validation
- observability
- scenario guidance
- diagnosis hints

### Fix applied
The troubleshooting approach changed so that benchmark outputs were read as a structured product telemetry layer.

This helped identify:
- what is really broken
- what is just missing coverage
- what is already good enough
- what must be fixed next for premium-ready

### Result
The benchmark tooling became much more useful as a development instrument, not just a release gate.

---

## 106. Systemd startup failed because the runtime blocked degraded wake compatibility mode


### Problem
The systemd unit started, but the assistant exited during startup instead of staying alive.

### Symptom
`nexa.service` briefly showed as active and then stopped.  
The journal showed a fatal startup error and boot acceptance failed.

### Root cause
The startup gate rejected the runtime because the assistant was still in a degraded wake configuration.

The critical journal message was effectively:
- primary runtime stack is not ready
- runtime degraded
- wake gate compatibility path active

So the issue was not that systemd itself was broken.  
The real issue was that runtime readiness policy treated the current wake configuration as not acceptable for the requested startup mode.

### Fix applied
I treated this first as a runtime-state problem, not as a deployment problem.

The debugging path focused on:
- reading `runtime_status.json`
- reading the service journal
- checking whether wake was running in compatibility mode or dedicated mode
- checking whether the service had become `failed`, `degraded`, `limited`, or truly `ready`

### Result
This made the service failure understandable and moved troubleshooting to the correct layer: runtime readiness, not unit installation.

---

## 107. Boot acceptance could fail even when the systemd unit file itself was installed correctly


### Problem
It was possible for deployment to look mostly correct while boot acceptance still failed.

### Symptom
Checks such as:
- `nexa.service:installed`
- `nexa.service:enabled`

could pass, while:
- `nexa.service:active`
- `runtime-product-state`

still failed.

### Root cause
Boot acceptance is stricter than simple systemd installation.

A valid unit file is not enough if the runtime itself ends in:
- `failed`
- `degraded`
- `blocked`
- `limited`
- `stopped`

### Fix applied
I treated boot acceptance as a product-runtime gate, not only as a deployment gate.

That means:
- passing install is not enough
- passing enablement is not enough
- passing service activation is not enough if the product state is still not healthy

### Result
This made deployment debugging more honest and prevented false confidence from “systemd looks installed” while the assistant still was not truly ready.

---

## 108. Voice input silently fell back to developer text mode when microphone initialization failed


### Problem
The assistant looked alive, but instead of acting like a voice assistant it exposed text-style interaction behaviour.

### Symptom
The runtime status showed:
- `voice_input` failed
- backend selected as `text_input`
- runtime mode like `developer_text_input`

The assistant could then behave as if it wanted typed commands in the terminal.

### Root cause
The real microphone path failed during initialization, and the runtime fell back to a developer-safe text input backend.

One key runtime message showed the failure clearly:
- no input audio devices available
- waited for audio input discovery
- last visible inputs: none

### Fix applied
I started diagnosing this through runtime status instead of guessing:
- inspect `var/data/runtime_status.json`
- inspect `services.voice_input`
- inspect `provider_inventory.voice_input`

This exposed whether the assistant was actually using:
- FasterWhisper microphone input
or
- fallback text input

### Result
The project became much easier to diagnose when voice disappeared, because the fallback mode was visible instead of silently misunderstood.

---

## 109. Display backend could fail because GPIO was still busy from an earlier process


### Problem
The display backend could fail even though the physical LCD hardware was fine.

### Symptom
Runtime status showed:
- `display` failed
- backend selected as `null_display`
- error similar to: `GPIO busy`

### Root cause
The GPIO lines needed by the display were still held by another process or by an earlier assistant instance that had not been cleaned up properly.

### Fix applied
I cleaned the runtime before restarting:
- stopped `nexa.service`
- killed any leftover `main.py` process
- checked for still-running assistant processes
- checked GPIO ownership
- then restarted the assistant cleanly

### Result
The real display backend could initialize again instead of falling back to `null_display`.

---

## 110. The microphone was healthy, but the runtime still needed explicit process cleanup before retesting
 

### Problem
There was a period where the assistant looked like it had lost microphone support, but the hardware itself was not actually the problem.

### Symptom
The assistant failed to use voice input and fell back to text mode.

### What I verified
I checked:
- `arecord -l`
- `sounddevice` input devices

and confirmed that the real microphone was available:
- `reSpeaker XVF3800 4-Mic Array`
- valid input channels
- default sample rate visible

### Root cause
The project was carrying stale runtime state and needed a clean restart path more than a hardware replacement.

### Fix applied
Before retesting, I used a stricter recovery sequence:
- stop systemd service
- kill leftover `main.py`
- wait briefly
- confirm no assistant process is still alive
- verify microphone devices again
- then run `python main.py`

### Result
The assistant recovered real voice input cleanly, and this proved the microphone itself was healthy.

---

## 111. The runtime could recover from blocked or degraded state after the real hardware paths were revalidated
 

### Problem
At different moments the runtime status moved through:
- `failed`
- `blocked`
- `degraded`
- `limited`

This made it easy to think the whole assistant was broken.

### Root cause
Those states were real, but they reflected intermediate recovery conditions rather than permanent project failure.

The assistant could degrade because of:
- text input fallback
- display fallback
- compatibility wake mode
- stale state after an interrupted run

### Fix applied
I treated runtime recovery as a sequence:
1. clean old processes
2. validate microphone visibility
3. validate display availability
4. rerun the assistant
5. re-read `runtime_status.json`

### Result
The runtime could move back upward from degraded startup into a healthier state once the real blocking condition was removed.

---

## 112. Real voice mode came back, but the system still honestly reported compatibility wake as degraded


### Problem
After microphone and display recovery, the assistant could again hear real speech and execute commands, but the runtime still reported a degraded or limited mode.

### Symptom
The assistant could successfully:
- wake
- listen
- recognize commands
- speak replies
- execute actions such as time and exit

but runtime status still reported something like:
- compatibility path active: wake_gate
- `startup_mode = limited`
- `premium_ready = false`

### Root cause
The system had recovered practical voice functionality, but it was still not using the desired dedicated wake path yet.

So the runtime was behaving honestly:
- usable assistant
- real microphone working
- but wake still not in the premium dedicated mode

### Fix applied
I did not treat this as a contradiction.

Instead, I accepted the distinction between:
- “works again”
and
- “premium-ready architecture restored”

### Result
This clarified the next task:
the project was no longer blocked by missing microphone or dead display,
but it still needed the dedicated wake path to be restored correctly before premium-ready status could be trusted.


---

## 113. Compatibility wake path proved that the voice pipeline still worked even when dedicated wake failed
 

### Problem
The assistant stopped reacting reliably on the dedicated wake path, which raised concern that the entire voice stack might be broken.

### Symptom
On the dedicated wake path, saying “NeXa” did not trigger the assistant even after repeated attempts.

### Root cause
At that stage it was not yet clear whether the problem was:
- the wake model
- the microphone
- the audio preprocessing
- or the wake runtime path itself

### Fix applied
I forced the system back onto the compatibility wake path and tested real microphone turns again.

### Result
The assistant successfully:
- detected wake
- listened for commands
- recognized commands
- spoke the reply
- completed follow-up flows such as exit confirmation

This was extremely important because it proved:
- the microphone was working
- STT was working
- command routing was working
- TTS was working
- the assistant was not generally “deaf”

The failure was therefore narrowed to the **dedicated wake path**, not the whole voice stack.

---

## 114. Dedicated OpenWakeWord path received real audio but produced almost zero wake scores


### Problem
The dedicated wake gate did not react to the wake phrase even though the runtime was healthy.

### Symptom
With wake debug enabled, the assistant printed traces such as:
- `raw=0.001`
- `smooth=0.001`
- `voiced` increasing
- repeated evaluations
- no actual wake trigger

### Root cause
The important observation was that the dedicated wake path **was receiving voiced audio**, but the model score stayed extremely low.

That meant:
- the assistant was not fully silent
- the wake path was not completely disconnected
- but something in the dedicated wake scoring path was not matching the spoken phrase properly

### Fix applied
I used the debug output not as a final fix, but as a narrowing tool:
- confirm audio is entering the wake path
- confirm the issue is score quality, not total absence of sound
- stop blaming unrelated layers such as TTS or LLM

### Result
The issue was narrowed from “voice is broken” to:
- “dedicated wake is hearing audio but not scoring it correctly”

---

## 115. The first suspicion was the model, but the working history of `nexa.onnx` argued for a regression first
  

### Problem
Because the dedicated wake path produced extremely low scores, it was tempting to assume that `models/wake/nexa.onnx` was bad.

### Symptom
Wake debug showed very weak scores and no practical activation on the dedicated path.

### Root cause
At first glance this could look like a broken or poor wake model.  
However, the project history mattered:
- the model had worked before
- earlier wake behaviour had been good enough to use
- the failure appeared after later pipeline and runtime changes

### Fix applied
I deliberately avoided treating model retraining or replacement as the first fix.  
Instead, the project switched to a regression-first mindset:
- check builder logic
- check config drift
- check wake backend selection
- check audio preprocessing
- check mono/channel handling
- check runtime path differences

### Result
This avoided an expensive and misleading conclusion.  
The working assumption became:
- `nexa.onnx` is not automatically guilty
- regression in the dedicated wake path must be checked first

---

## 116. Rollback attempts failed at first because the wake path configuration combination was wrong
 

### Problem
I attempted to roll the system back from dedicated wake to compatibility wake, but the assistant still launched the dedicated OpenWakeWord backend.

### Symptom
Even after editing the configuration, runtime status still reported:
- `selected_backend = openwakeword`
- `runtime_mode = dedicated_wake_gate`

### Root cause
The rollback settings were initially changed to the wrong combination.

The intended rollback required the configuration to align with how the runtime builder selected the wake path.  
Using the wrong combination caused the runtime to stay on the dedicated path even though the intention was to test compatibility mode.

### Fix applied
The wake configuration was corrected to the combination that actually activates compatibility wake in the current runtime path selection logic.

### Result
Once the correct values were applied, the assistant finally switched onto:
- `compatibility_voice_input`
- `single_capture_compatibility`

This confirmed that the earlier rollback had failed because of **config interaction**, not because rollback itself was impossible.

---

## 117. `single_capture_mode` turned out to be a real wake-path switch, not just a capture convenience setting


### Problem
At first, `single_capture_mode` could be misread as only a general audio-capture preference.

### Symptom
Changing `single_capture_mode` changed much more than expected:
- wake path behaviour
- compatibility reuse of the main voice input
- whether the runtime stayed in a degraded but working wake mode

### Root cause
In practice, `single_capture_mode` participates directly in wake path selection.

That means it does not only affect how input is captured.  
It also influences whether wake detection:
- reuses the main voice input backend
or
- goes through a dedicated wake pipeline

### Fix applied
I started treating `single_capture_mode` as a high-impact routing control rather than a minor capture tweak.

### Result
This made wake-path debugging much clearer and reduced confusion about why the assistant changed behaviour after seemingly small config edits.

---

## 118. Wake path preference logic drifted and needed to be made explicit again


### Problem
The project needed a predictable way to choose between:
- compatibility wake
- dedicated wake

but the path preference became confusing over time.

### Symptom
The runtime behaviour did not always match the operator’s expectation after config edits.  
This made it hard to tell whether the correct wake path was truly being tested.

### Root cause
Wake path selection was effectively being driven by a combination of builder logic and runtime settings, but the preference rules were not sufficiently explicit and easy to reason about during troubleshooting.

### Fix applied
The wake-path preference logic was clarified so that:
- compatibility wake can be selected intentionally for recovery or diagnosis
- dedicated wake can be selected intentionally for premium-path validation
- the chosen route is reflected clearly in runtime status

### Result
Wake path testing became controlled instead of ambiguous.  
This was necessary to fairly compare:
- “known-good fallback path”
versus
- “premium dedicated wake path”

---

## 119. Compatibility wake worked, but it was too slow to ever satisfy premium wake targets


### Problem
Compatibility wake provided a working recovery path, but that did not mean it was a premium-ready solution.

### Symptom
With compatibility wake active, the assistant could function correctly, but benchmark results still showed that premium voice targets were not met.

The critical issue was wake latency:
- wake worked
- but the average wake time stayed far above the premium target

### Root cause
Compatibility wake reuses the main voice input path.  
This is useful for recovery and diagnosis, but it is not the dedicated low-latency wake architecture the premium release is targeting.

### Fix applied
I explicitly separated the meanings of:
- “works”
and
- “premium-ready”

Compatibility wake was accepted as a valid diagnostic and fallback path, but not as the final target for release quality.

### Result
This clarified the roadmap:
- compatibility wake is good enough to keep development moving
- but **11.1 / 4 cannot be considered complete at premium level until dedicated wake is restored and fast again**


## 120. UGV02 was visible over USB serial, but the first movement tests did not move the chassis
 

### Problem
After connecting the mobile base to Raspberry Pi through USB-C, the base was visible to the system but did not move during the first hardware tests.

### Symptom
The project could communicate with the base, but the chassis still stayed still.

The important observations were:
- the Pi detected the controller at `/dev/ttyACM0`
- serial communication worked
- telemetry queries returned valid JSON feedback
- the chassis still did not move during the first movement attempts

### Root cause
The problem was not a dead USB connection.

The real issue was that:
- the correct serial device was `/dev/ttyACM0`, not `/dev/ttyUSB0`
- the first manual movement path was not the most reliable control path for this base
- the base responded better when driven through the working repeated streamed movement command flow

### Fix applied
I switched diagnosis and control toward:
- explicit serial setup at `115200`
- the correct `/dev/ttyACM0` path
- repeated streamed motion commands
- explicit stop commands
- mobility calibration through manual hardware tests

### Result
The Raspberry Pi could command the UGV02 successfully and the base started moving under project-side software control.


## 121. UGV02 AP mode looked confusing even though the hotspot was active
 

### Problem
The mobile base looked like it had networking issues because the control page at `192.168.4.1` did not load immediately.

### Symptom
The OLED showed:
- `AP: UGV`
- `ST: off`

but the browser page did not open at first.

### Root cause
The meaning of the OLED status was misunderstood.

`AP: UGV` means the base is exposing its own Wi-Fi hotspot.  
`ST: off` means it is not connected to another router as a station.

The page at `192.168.4.1` is only reachable when the phone or laptop is actually connected to the `UGV` access point.

### Fix applied
I clarified the networking model:
- find the `UGV` Wi-Fi network on the client device
- connect to that network
- then open `192.168.4.1`

### Result
The Wi-Fi behaviour became understandable and no longer looked like a random connectivity failure.

## 122. BOOT button was pressed during normal runtime and could leave the base in the wrong state
 

### Problem
The base reacted a few times and then became inconsistent after the BOOT button had been pressed during normal use.

### Symptom
The chassis could:
- react briefly
- then stop reacting
- appear confusing to recover
- make it unclear whether the problem was software or hardware

### Root cause
The BOOT button is associated with special controller state handling and should not be used as a normal runtime reset action.

In the assembled hardware setup, the normal reset path was not obvious, which made recovery more confusing.

### Fix applied
I changed the practical recovery rule:
- avoid using BOOT for normal recovery
- use a full power cycle for clean recovery
- reconnect USB after the base has restarted cleanly
- continue diagnosis from a known clean startup state

### Result
Recovery became safer and more repeatable.


## 123. Desk-surface slip caused open-loop turn tests to under-rotate


### Problem
The first turn test was not accurate enough on the desk surface.

### Symptom
The expected turn behaviour did not match the real chassis motion:
- a nominal 90-degree turn could behave closer to about 45 degrees
- a nominal full spin could behave closer to about 180 degrees

### Root cause
The initial turn test used open-loop timing assumptions.

On a desk surface, real chassis rotation is affected by:
- wheel slip
- friction variation
- angular command strength
- short motion timing sensitivity

A single shared angular calibration value was not good enough for:
- quarter turns
- full spin

### Fix applied
The motion test direction was improved by:
- separating turn calibration from straight motion
- splitting quarter-turn calibration from full-spin calibration
- lowering angular command strength for safer behaviour
- exposing calibration parameters in the manual test layer

### Result
The test path became much more usable for manual calibration, even though it is still not the final motion runtime.

### Follow-up
The final premium solution should later move toward a dedicated transport service with better closed-loop support where practical.


## 124. Mobility validation was intentionally kept outside the main assistant runtime


### Problem
There was a risk of mixing early chassis control directly into the main assistant runtime before the mobility layer was properly validated.

### Symptom
Without separation, it would be too easy to confuse:
- hardware problems
- serial problems
- control calibration problems
- assistant runtime problems

### Root cause
The mobility layer is still in a validation stage and should not yet be merged into high-level assistant orchestration as if it were already production-ready.

### Fix applied
I kept the mobility validation in dedicated manual test paths under:
- `tests/hardware/ugv02/`

This allowed safe isolation of:
- port detection
- movement command testing
- desk-safe calibration
- turn and spin tuning

### Result
The mobility work no longer risks destabilising the core voice runtime while the base is still being calibrated.


## 125. The UGV02 serial JSON boundary proved to be the correct integration direction
 

### Problem
The project needed a clean way to integrate the mobile base without mixing assistant logic directly with low-level chassis control.

### Symptom
At first, it was not yet clear whether the best direction would be:
- direct mixed motor logic in the assistant flow
or
- a cleaner hardware boundary

### Root cause
As the project becomes more embodied, hardware boundaries matter more.

Without a clean boundary, mobility would become harder to:
- debug
- test
- calibrate
- extend safely

### Fix applied
The practical architecture direction was clarified:
- Raspberry Pi talks to the UGV02 through the serial JSON control boundary
- the ESP32 driver board remains the low-level chassis controller
- NeXa should later integrate mobility through a dedicated client or transport service

### Result
The mobility integration now has a cleaner architectural direction and fits the overall NeXa modular design much better.

# Vision Troubleshooting

This file lists the main problems we had while building the camera and vision foundation for NeXa, what caused them, and how we fixed them.

---

## 1. Permission error for `system.log`

### Symptom
Tests failed before the vision code even started.

### Error
PermissionError: [Errno 13] Permission denied: '/home/devdul/Projects/smart-desk-ai-assistant/var/logs/system.log'
Cause

The logger tried to open the log file during import.
If the normal user did not have permission to write to that file, the import failed and the tests stopped.

### Fix

We changed the logger so it can safely fall back to stderr if the log file is not available.

### Result

The warning can still appear, but it no longer breaks tests or the vision system.

### 2. Vision package imported too much too early
Symptom

A simple import triggered a long chain of other imports:

CameraService
capture reader
logger
backend modules

This made tests fragile.

### Cause

__init__.py files in the vision package were using eager imports.

### Fix

We changed the imports to lazy loading with __getattr__.

### Result

Imports are lighter and safer now.

### 3. ModuleNotFoundError in the camera smoke test
Symptom

pytest worked, but the hardware smoke script failed when run directly.

### Error
ModuleNotFoundError: No module named 'modules'
Cause

When Python ran the script directly, the project root was not added to sys.path.

### Fix

We added a small repo-root bootstrap at the top of the hardware smoke script.

### Result

The smoke script can now be run directly with:

python tests/vision/hardware/camera/camera_capture_smoke.py
### 4. Mutable default error in PerceptionPipeline
Symptom

The perception tests failed during test collection.

### Error
ValueError: mutable default <class '...NullSceneAnalyzer'> for field scene_analyzer is not allowed: use default_factory
Cause

We used object instances as default values inside a dataclass, for example:

NullPeopleDetector()
NullObjectDetector()
NullSceneAnalyzer()

That is not safe in Python dataclasses.

### Fix

We changed those fields to use field(default_factory=...).

### Result

The dataclass is now valid and the tests can run correctly.

### 5. vars() failed with slots=True
Symptom

The perception pipeline still failed after the first fix.

### Error
TypeError: vars() argument must have __dict__ attribute
Cause

NormalizedRegion uses slots=True, so it does not have a normal __dict__.
Because of that, vars(...) could not be used on it.

### Fix

We replaced vars(...) with a small helper function that builds a normal dictionary by hand.

### Result

Scene metadata now serializes correctly.

### 6. No clear runtime contract for vision
Symptom

Vision worked, but it did not yet have a proper runtime contract like the other backends.

### Cause

There was no dedicated VisionBackend protocol, and the null backend was too simple.

### Fix

We added a clear runtime contract for vision:

latest_observation(...)
status()
close()

We also updated NullVisionBackend so it matches the real backend better.

### Result

Vision is now cleaner and easier to plug into runtime code.

### 7. Camera service was too easy to break on a capture error
Symptom

A temporary camera read problem could break the flow too hard.

### Cause

The first version of CameraService did not keep a good fallback state when capture failed.

### Fix

We improved CameraService so it:

stores last_error
keeps the last good observation
returns cached data if a refresh fails
reports more details in status()
Result

The service is more stable and more product-ready now.

### 8. Vision output was too simple at first
Symptom

The camera worked, but the output was only a basic "camera online" snapshot.

### Cause

The first fusion step did not yet include perception structure.

### Fix

We added:

PerceptionSnapshot
PerceptionPipeline
scene context
workspace zones
semantic fusion

### Result

The system is now ready for the next vision features:

person at desk
phone usage
computer work
study activity logic



## 126. Raspberry Pi 5 showed a high-current USB boot warning when powered through X1206
 

### Problem
When NeXa was powered through the X1206 battery-backed UPS path instead of a normal high-current USB-C supply, Raspberry Pi 5 showed a boot-time warning about USB boot requiring a high-current power supply.

### Symptom
The system displayed a warning similar to:

- `USB boot requires high current (5 volt 5 amp) power supply`
- `power: supply: Unknown 3000 mA`

This created uncertainty about whether:
- the batteries were too weak
- the UPS was not suitable
- the SSD boot path would remain stable
- USB-connected components might be power-limited

### Root cause
The main issue was not simply the battery cells themselves.

In practice, Raspberry Pi 5 was not identifying the X1206 battery-backed path as a normal 5V / 5A high-current source in the same way as an official USB-PD supply.

Because of that, the Pi could apply a more conservative power policy during USB boot and for USB power budgeting, even though the X1206 path could still be practically usable.

### What I tested
I checked:
- EEPROM power configuration
- `/boot/firmware/config.txt`
- runtime throttling state
- voltage-related kernel messages
- X1206 battery telemetry

The main validation commands included:
- `sudo -E rpi-eeprom-config --edit`
- `grep -n "usb_max_current_enable" /boot/firmware/config.txt`
- `sudo rpi-eeprom-config | grep PSU_MAX_CURRENT`
- `vcgencmd get_throttled`
- `dmesg | grep -i voltage`
- `python /home/devdul/x120x/bat.py`

### Fix applied
I updated the Raspberry Pi 5 power policy so that the system would not stay in the reduced-current assumption for this battery-backed setup.

The applied changes were:
- set `PSU_MAX_CURRENT=5000` in EEPROM
- set `usb_max_current_enable=1` in `/boot/firmware/config.txt`

After that I rebooted and verified:
- `PSU_MAX_CURRENT=5000`
- `usb_max_current_enable=1`
- `throttled=0x0`

### Result
After the power-policy update:
- the configuration state was correct
- the runtime reported `throttled=0x0`
- `dmesg | grep -i voltage` did not show undervoltage warnings
- X1206 battery telemetry looked stable during the observed test
- later battery telemetry showed about `4.03V` and `84%`

This indicated that the practical runtime state was healthy after the configuration fix.

### Follow-up
This should not be treated as proof that power can never become a limit under heavier future load.

The correct practical rule is:
- keep the override in place for X1206-based battery operation
- test again under full NeXa load with SSD and connected peripherals
- keep watching for:
  - throttling
  - undervoltage warnings
  - SSD instability
  - audio or USB instability

This issue clarified that the first problem was mainly Raspberry Pi 5 power-source policy and detection behaviour, not only raw battery quality.
---

## Observation — duplicate [audio] section in godot_app/project.godot

Date: 2026-04-30
Severity: low (not an active problem; Godot tolerates and uses the second occurrence)

Symptom:
modules/presentation/visual_shell/godot_app/project.godot contains two
identical [audio] sections back-to-back:

  [audio]
  driver/driver="Dummy"
  driver/enable_input=false

  [audio]
  driver/driver="Dummy"
  driver/enable_input=false

Risk:
- Confusing for future edits.
- A future merge/rebase that touches one of the two will be silently lossy.

Resolution (when convenient, not urgent):
Open the file and remove the duplicate block. No runtime impact expected
since both sections are identical.

<!-- BEGIN NEXA_GUIDED_REMINDER_AND_MEMORY_TROUBLESHOOTING -->

## Guided reminder and memory troubleshooting

### Problem: runtime candidate executor returned no plan for valid commands

Symptoms:

- `what is your name` was recognized as `assistant.identity`, but no execution plan was built.
- `what time is it` was recognized as `system.current_time`, but no execution plan was built.
- `show desktop` and `hide desktop` were recognized but rejected at plan-building level.
- Multiple runtime candidate executor tests failed from the same root cause.

Root cause:

`RuntimeCandidateExecutionPlanBuilder.build_plan()` checked `turn_result.is_match`, but `VoiceTurnResult` does not expose `is_match`. That property exists on `CommandRecognitionResult`.

Broken gate:

`getattr(turn_result, "is_match", False)`

Because `VoiceTurnResult` did not have this attribute, the check returned `False` and valid commands were rejected unless a transcript override bypassed the gate.

Fix:

Use intent presence on `VoiceTurnResult`:

`getattr(turn_result, "intent", None) is None`

Validation:

- `pytest -q tests/runtime/voice_engine_v2/test_runtime_candidate_executor.py`
- `pytest -q tests/runtime/voice_engine_v2/test_runtime_candidates.py`

### Problem: unfinished Visual Shell runtime-only intents failed tests

Symptoms:

- `show yourself` routed to face contour instead of `show_self`.
- `pokaż oczy`, `spójrz na mnie`, and `scan room` did not build runtime candidate plans.
- Public Visual Shell intent tests still required these commands to stay unpublished.

Root cause:

Some Visual Shell actions are intentionally not public yet. They must not be exposed in public command intent definitions or public grammar, but they can exist as runtime-candidate-only executor specs.

Fix:

- Add specs only in `RuntimeCandidateExecutionPlanBuilder._SPECS`.
- Add selected transcript overrides in the runtime candidate executor.
- Do not add these unfinished intents to public Visual Shell intent definitions.
- Do not add these unfinished intents to public command grammar.

Validation:

- `pytest -q tests/runtime/voice_engine_v2/test_runtime_candidate_executor.py`
- `pytest -q tests/core/command_intents/test_visual_shell_intents.py::test_unfinished_visual_shell_intents_are_not_public -vv`

### Problem: reminder candidate could be accepted without execution plan

Symptoms:

A duplicate `if reminder_intent_key:` branch in `runtime_candidates.py` could create `VoiceEngineV2RuntimeCandidateResult(accepted=True)` without an `execution_plan`.

Root cause:

`VoiceEngineV2RuntimeCandidateResult` requires an execution plan whenever `accepted=True`. The duplicate branch was fragile and could become a runtime crash if the builder did not return a plan.

Fix:

Remove the dead duplicate branch and keep reminder candidates on the safe builder path.

Validation:

- `pytest -q tests/runtime/voice_engine_v2/test_runtime_candidates.py`
- `pytest -q tests/features/test_reminder_vosk_runtime_candidate_policy.py`
- `pytest -q tests/features/test_reminder_vosk_fast_path_policy.py`

### Problem: reminder start recognized by Vosk but legacy telemetry still showed fallback

Symptoms:

`vosk_pre_whisper_candidate` showed:

- `accepted=true`
- `intent_key=reminder.guided_start`
- `route=guided_reminder`
- `llm_prevented=true`
- `faster_whisper_prevented=true`

But separate telemetry also showed:

`fallback_required:unknown_intent:reminder.guided_start`

Explanation:

The pre-whisper Vosk fast path accepted the guided reminder start correctly. Older legacy candidate telemetry may still report fallback because it does not fully own the reminder guided flow yet.

Important signal:

Use `vosk_pre_whisper_candidate accepted=true` with `faster_whisper_prevented=true` as the fast-path success signal.

### Problem: reminder time mixes Polish and English

Symptoms:

Runtime candidate telemetry may show mixed alternatives such as:

`eight seconds | pięć sekund`

or normalized mixed text:

`eight seconds piec sekund`

Root cause:

The `reminder_time` capture can evaluate time answers without locking recognition to the active guided flow language. This can create ambiguous mixed-language results.

Required follow-up:

- Carry active guided flow language into `reminder_time` capture metadata.
- Pass the language hint into Vosk pre-whisper candidate recognition.
- Use language-specific command grammar/model for time answers.
- Reject mixed-language time candidates.
- Keep response templates in the same language as the active flow.

Expected behavior:

- English flow accepts English time answers only.
- Polish flow accepts Polish time answers only.
- Mixed PL/EN reminder time candidate must not be accepted.

### Planned memory troubleshooting rules

Memory should be debugged with the same principles as reminders:

- If memory start command is not recognized, check Vosk grammar aliases for `memory.guided_start`.
- If memory content is empty, check the guided memory capture profile.
- If recall returns nothing, inspect normalized tokens stored with each memory entry.
- If Polish recall finds English memories or English recall finds Polish memories, check language filtering.
- If memory delete or clear runs without confirmation, treat it as a safety bug.
- If LLM is used for simple memory save or recall, treat it as a runtime architecture regression.
<!-- END NEXA_GUIDED_REMINDER_AND_MEMORY_TROUBLESHOOTING -->

<!-- BEGIN guided-reminder-memory-troubleshooting -->
## Guided reminders and guided memory troubleshooting

### Reminder runtime candidate rejected with `unknown_intent:reminder.guided_start`

Observed symptom:

- Vosk recognizes `set reminder`.
- Runtime candidate log shows `recognized=true`.
- Candidate is rejected with `fallback_required:unknown_intent:reminder.guided_start`.

Root cause found during repair:

- `RuntimeCandidateExecutionPlanBuilder.build_plan()` used `turn_result.is_match`.
- `VoiceTurnResult` does not expose `is_match`; it exposes `is_command` / `is_fallback`.
- `is_match` belongs to lower-level command recognition results.
- This made valid command turns appear invalid unless transcript overrides bypassed the gate.

Fix:

- Gate on presence of `turn_result.intent` instead of non-existing `turn_result.is_match`.
- Add reminder specs to runtime candidate execution specs.
- Remove dead duplicate reminder acceptance block from runtime candidates.

### Visual Shell runtime candidate mismatches

Observed symptoms:

- `show yourself` mapped to `visual_shell.show_face`.
- `show the time` returned no execution plan.
- Some unfinished Visual Shell actions were not public grammar intents.

Decision:

- Do not add unfinished Visual Shell intents to public command intent definitions or public grammar.
- Keep unfinished actions as runtime-candidate-only specs.
- Route selected phrases through transcript overrides where required.

This preserves `test_unfinished_visual_shell_intents_are_not_public`.

### Settings JSON has `Extra data` after patch

Observed symptom:

- `json.loads(Path("config/settings.json").read_text())` fails with `JSONDecodeError: Extra data`.
- The file ends with literal trailing text like `\n`.

Fix:

- Parse the first JSON object with `json.JSONDecoder().raw_decode(...)`.
- Rewrite the file using `json.dumps(..., indent=2) + "\n"`.
- Do this for both `config/settings.json` and `config/settings.example.json`.

### Guided memory expectations

Guided memory should behave like guided reminders:

- `zapamiętaj coś` / `remember something` starts a follow-up.
- NEXA asks what to remember in the same language.
- The next utterance is saved as a full phrase.
- Recall searches by tokens, not only exact keys.
- Polish and English records must remain separated per turn.
- No silent memory save failures are acceptable.

If memory recall fails unexpectedly:

1. Check `var/data/memory.json` shape.
2. Confirm it is either a legacy dict or a list of memory records.
3. Confirm records include `language`, `original_text`, `normalized_text`, and `tokens`.
4. Confirm the recall language matches the stored record language.
5. Run `pytest -q tests/unit/services/test_memory.py`.
<!-- END guided-reminder-memory-troubleshooting -->

<!-- BEGIN feedback-dashboard-and-visual-shell-troubleshooting -->
## Feedback Mode and Visual Shell display troubleshooting

### Feedback commands go through confirmation

Observed symptoms:

- The user says feedback on or feedback off.
- The transcript may be heard as Feed back on, Oruham feedback, Oruham Fitbit, Feedback of, Feed the back of, Sheet back off or Sheets back off.
- The assistant asks for confirmation instead of executing immediately.
- The action feels slow because the flow waits for yes or no.

Root cause:

- Common ASR variants were missing from the deterministic command alias layer.
- The command fell into parser suggestion or confirmation flow instead of FastCommandLane.

Fix:

- Add feedback aliases to FastCommandLane.
- Add parser phrases for feedback ASR variants.
- Add safe Vosk grammar variants only when the model vocabulary supports them.
- Keep unsupported Polish-like ASR variants in the post-STT fast alias layer.

Expected behavior:

- feedback on, feed back on, feedback own, oruham feedback and oruham fitbit start Feedback Mode without LLM and without confirmation.
- feedback off, feedback of, feed back off, feed the back of, sheet back off and sheets back off close Feedback Mode without LLM and without confirmation.
- Fast command telemetry should show deterministic action handling.

### Feedback dashboard logs are difficult to read

Observed symptoms:

- Live logs keep appending while the user scrolls up.
- The log view jumps back to the bottom whenever a new log arrives.
- The user cannot inspect earlier log entries.
- Camera logs mix into general system logs.

Root cause:

- The log view always followed new entries.
- There was no scroll lock while reviewing old entries.
- Vision, camera, detector and capture logs were not separated clearly.
- Log entries were too dense for the DSI display.

Fix:

- Add bounded log retention.
- Keep only recent dashboard logs, currently around five minutes, with an additional maximum entry limit.
- Preserve scroll position when the user has scrolled up.
- Route vision, camera, detector and capture logs to the Vision tab.
- Add spacing between log entries.

Expected behavior:

- Live logs continue to update.
- The log view does not jump to the bottom while the user reviews older entries.
- Vision logs appear under VISION LOG.
- General runtime logs appear under SYSTEM LOGS AND STATUS.

### Feedback dashboard freezes after feedback off

Observed symptoms:

- The user says feedback off.
- Runtime reports FEEDBACK closed.
- The dashboard remains visible or appears frozen.

Root cause:

- Background feedback workers and visual hide commands were not ordered defensively.
- A hide command could be missed while the Visual Shell was busy.

Fix:

- Send HIDE_FEEDBACK immediately when Feedback Mode turns off.
- Stop feedback status and vision workers.
- Detach the feedback log handler.
- Send HIDE_FEEDBACK again after cleanup.
- Hide both the dashboard view and dashboard layer in Godot.

Expected behavior:

- feedback off hides the dashboard immediately.
- Worker shutdown happens safely.
- Repeated feedback off commands are safe.

### Visual Shell commands fail with renderer unavailable

Observed symptoms:

- Voice command is recognized correctly.
- Logs show transport_result=failed.
- Logs show reason=renderer_unavailable.
- show desktop or feedback commands do not affect the renderer.

Root cause:

- Godot Visual Shell is not running, failed to bind TCP, or a stale Godot process is running without listening on port 8765.
- A stale process can appear in pgrep while ss shows no listener.

Diagnostic commands:

    pgrep -af "godot3|visual_shell" || true
    ss -ltnp 2>/dev/null | grep ":8765" || true
    tail -n 120 var/logs/visual_shell_manual.log

Fix:

- Kill stale Godot processes whose current working directory is modules/presentation/visual_shell/godot_app.
- Remove the stale Visual Shell lock.
- Restart Visual Shell from modules/presentation/visual_shell/bin/run_visual_shell.sh.
- Confirm that port 127.0.0.1:8765 is listening.

Expected behavior:

- show desktop, hide desktop, feedback on and feedback off send TCP commands successfully.
- Logs show transport_result=ok.

### Visual Shell appears halfway down the DSI display

Observed symptoms:

- The Visual Shell window exists and has size 1280x800.
- xdotool may report the window at position 0,0.
- Visually, the shell appears partly off-screen or starts halfway down the DSI display.

Root cause:

- The desktop is a combined virtual display.
- In the current DSI plus HDMI setup, xrandr reports DSI-2 at 1280x800+0+360.
- HDMI-A-1 is placed at 2560x1440+1280+360.
- The combined virtual desktop size is 3840x1800.
- Global coordinate 0,0 is above the physical DSI output.
- The Visual Shell must target the DSI output geometry, not global 0,0.

Fix:

- Detect the target output geometry from xrandr.
- Use DSI-2 as the default Visual Shell output.
- Start the full shell at the detected DSI output offset, for example 0,360.
- Export detected geometry to Godot through environment variables.
- Compute docked mode inside the DSI output bounds.

Expected behavior:

- Full Visual Shell covers the DSI screen.
- show desktop docks the assistant inside the DSI top-right corner.
- hide desktop restores the full shell to the DSI geometry.
- The shell no longer appears halfway off-screen.

Useful verification:

    xrandr --current
    PID="$(pgrep -n -f 'godot3.*--path .')"
    for WID in $(xdotool search --pid "$PID" 2>/dev/null || true); do
      xdotool getwindowgeometry "$WID"
    done
    ss -ltnp 2>/dev/null | grep ":8765" || true

### ESC does not close the Visual Shell

Observed symptoms:

- Pressing ESC does not close the Visual Shell.
- This can happen when an overlay or control has focus.

Root cause:

- Depending only on _input is not robust enough when UI controls consume input.
- If Godot scripts fail to parse, ESC cannot work because the main shell script is not loaded.

Fix:

- Add keyboard handling through _input, _unhandled_input, _unhandled_key_input and process-level polling.
- Ensure the Godot project has no script parse errors.
- Check var/logs/visual_shell_manual.log for SCRIPT ERROR before debugging keyboard handling.

Expected behavior:

- ESC closes the Godot Visual Shell.
- The log may show Visual Shell quit requested by ESC.
<!-- END feedback-dashboard-and-visual-shell-troubleshooting -->

<!-- BEGIN pan-tilt-gpio-uart-troubleshooting -->
## Issue - Waveshare pan-tilt did not move through USB but worked through Dashboard

**Date:** 2026-05-02  
**Area:** pan-tilt / GPIO UART / Waveshare General Driver  
**Status:** resolved for hardware communication path  

**Problem**  
The Waveshare pan-tilt worked from the web Dashboard over hotspot, but did not move when NEXA test scripts sent JSON commands over USB.

**Symptoms**

- Dashboard JSON commands moved the pan-tilt correctly.
- Servo ID calibration eventually worked:
  - TILT servo = ID 1
  - PAN servo = ID 2
- USB tests showed serial telemetry, but physical movement did not happen.
- USB `T:210` torque lock did not lock the pan-tilt servos.
- USB `T:133` and `T:141` movement commands did not move the pan-tilt.
- The USB serial log included fields such as `L`, `R`, `odl`, `odr`, `pan` and `tilt`.
- After unplugging the mobile base USB, the only visible USB serial port disappeared.

**Root cause**  
The USB serial port originally used by the test scripts was the mobile base serial device, not the pan-tilt control path. The pan-tilt itself was working through its WiFi Dashboard, but it was not visible to Raspberry Pi as the expected USB serial control device.

A charging-only USB-C cable also complicated diagnosis because it did not expose a reliable USB data connection.

**What was tested**

- Dashboard JSON servo lock/unlock.
- Dashboard servo ID checks.
- Dashboard small axis movement.
- USB serial device enumeration through:
  - `/dev/serial/by-id`
  - `/dev/serial/by-path`
  - `/dev/ttyUSB*`
  - `/dev/ttyACM*`
  - `lsusb`
  - passive serial reads.
- USB echo/debug commands.
- GPIO UART availability.
- Linux serial console removal from `/dev/serial0`.
- GPIO UART passive telemetry.
- GPIO UART echo/status commands.
- GPIO UART torque lock/unlock.
- GPIO UART tiny movement sequence.

**Fix applied**

- The pan-tilt communication path was moved to Raspberry Pi GPIO UART.
- `/dev/serial0` was freed from Linux serial console usage.
- `enable_uart=1` was added to boot config.
- serial getty was disabled/inactive.
- The confirmed runtime path is now `/dev/serial0`.
- USB auto-detection must not be used for pan-tilt while the mobile base can expose a similar serial device.

**Confirmed working result**

- `/dev/serial0 -> ttyAMA0`
- `console=tty1`
- no `console=serial0,115200`
- GPIO UART receives `T:1001` telemetry.
- GPIO UART echoes JSON commands.
- `T:210 cmd:1` locks the pan-tilt servos.
- `T:210 cmd:0` unlocks the pan-tilt servos.
- Tiny movement over GPIO UART works.

**Important safety note**

The pan-tilt must not run full sweeps or large angle tests by default. The safe validation sequence is tiny movement only:

- right
- center
- left
- center
- up
- center
- down
- center
- stop

The first production backend must remain config-driven, conservative, and guarded by calibration/safety limits.
<!-- END pan-tilt-gpio-uart-troubleshooting -->

---

## Vision Runtime Sprint 2 — Pytest import mismatch caused by duplicate test module name

**Date:** 2026-05-05  
**Area:** vision / tests / pytest collection  
**Status:** resolved

### Problem

After adding the new VisionTrackingService tests, the broader test run failed during Pytest collection.

### Symptom

Pytest reported an import file mismatch between:

- tests/vision/unit/tracking/test_service.py
- tests/vision/unit/camera_service/test_service.py

The error happened before the full suite could run.

### Root cause

Two test files had the same basename:

- test_service.py

Pytest imported the tracking test module first as test_service, then tried to collect the camera service test file with the same module name.

This created a module-name collision during collection.

### Fix applied

The new tracking service test file was renamed from:

- tests/vision/unit/tracking/test_service.py

to:

- tests/vision/unit/tracking/test_tracking_service.py

The Python cache directories were also removed to avoid stale import state.

### Result

The test collection issue was resolved.

The broader vision, pan-tilt, Visual Shell, and Voice Engine v2 runtime candidate test set passed after the rename.

### Follow-up rule

New test files should use specific names when another package already contains a generic test name such as test_service.py.

For future NEXA Vision Runtime work, prefer names like:

- test_tracking_service.py
- test_pan_tilt_tracking_policy.py
- test_scan_planner.py
- test_base_yaw_assist_policy.py

This reduces the chance of Pytest import collisions.

---

## Vision Runtime Sprint 3B — first runtime metadata patch stopped with exit code 1

**Date:** 2026-05-05  
**Area:** vision / runtime builder / patch safety  
**Status:** resolved

### Problem

The first attempt to patch runtime builder metadata stopped with terminal exit code 1.

### Symptom

The terminal process ended with:

- exit code: 1

The runtime files were not changed.

### Root cause

The first patch used a large exact text replacement against runtime builder files.

The real repository file structure did not match that exact anchor text closely enough, so the safety script stopped instead of applying a blind change.

This was expected safe behaviour from the patch guard.

### What I checked

I checked:

- latest backup directory
- git status
- git diff for runtime builder files
- Python syntax compilation for the affected files

The result showed:

- git status was clean
- git diff was empty
- py_compile passed

So the failed attempt did not corrupt the repository.

### Fix applied

The Sprint 3B patch was rewritten with smaller and more defensive anchors.

The retry patch:

- inserted _build_vision_tracking before the RuntimeBuilderVisionMixin export marker
- added vision_tracking_cfg to the runtime builder
- built VisionTrackingService after pan-tilt construction
- added vision_tracking to backend statuses
- exposed vision_tracking_service and vision_tracking_status in runtime metadata
- added an integration test for the builder bridge

### Result

The retry patch passed the relevant tests.

### Follow-up rule

For runtime builder changes, avoid one large exact replacement when the file may have evolved.

Use smaller anchors and fail loudly if an expected insertion point is missing.

This keeps NEXA runtime patches safer and reduces the risk of damaging core startup logic.

---

## Vision Runtime Sprint 6B — settings defaults test did not handle typed assignment

**Date:** 2026-05-05  
**Area:** vision / settings / tests  
**Status:** resolved

### Problem

The Sprint 6B settings contract test failed while reading:

- modules/shared/config/settings_core/defaults.py

### Symptom

The failing test was:

- test_default_settings_define_safe_vision_tracking_execution_gates

The error was:

- Could not find the main defaults settings dictionary.

### Root cause

The test helper parsed defaults.py with ast and only handled normal assignment nodes.

It expected a pattern equivalent to:

DEFAULT_SETTINGS = dict

But the real defaults file uses a typed assignment pattern, represented in Python AST as AnnAssign.

The helper did not handle AnnAssign, so it could not find the settings dictionary even though the config patch had been applied.

### Fix applied

The test helper was updated to support both:

- ast.Assign
- ast.AnnAssign

After that, the test correctly found the main defaults dictionary and verified the new vision_tracking contract.

### Result

The focused settings contract tests passed.

The broader vision, runtime, pan-tilt, Visual Shell, and Voice Engine v2 test set also passed.

### Follow-up rule

When testing Python config files through ast, support both regular assignments and typed assignments.

This avoids false failures when the project uses type-annotated settings constants.

---

## Vision Runtime Sprint 7A — importlib test loader broke dataclass annotations on Python 3.13

**Date:** 2026-05-05  
**Area:** vision / tests / validator / Python 3.13  
**Status:** resolved

### Problem

The new readiness validator tests failed when importing:

- scripts/validate_vision_tracking_execution_readiness.py

### Symptom

The focused validator tests failed with an AttributeError from dataclasses:

- NoneType object has no attribute __dict__

The failure happened when the test loaded the script with importlib and the script defined a dataclass.

### Root cause

The test used importlib.util.module_from_spec and spec.loader.exec_module, but did not register the module in sys.modules before executing it.

With Python 3.13, dataclass processing with postponed annotations can look up the module through sys.modules.

Because the module was not registered, dataclasses could not find the module namespace during class processing.

### Fix applied

The test loader was updated to register the module before execution:

- sys.modules[spec.name] = module
- spec.loader.exec_module(module)

After this change, the validator module loaded correctly and all validator tests passed.

### Result

The focused validator tests passed.

The broader vision, runtime, pan-tilt, Visual Shell, and Voice Engine v2 test set also passed.

### Follow-up rule

When tests load script files with importlib and those scripts define dataclasses, register the module in sys.modules before exec_module.

This avoids false failures in Python 3.13 and keeps script-style validator tests reliable.

---

## Vision Runtime Sprint 9B — tiny smoke preview found non-centered calibration state

**Date:** 2026-05-05  
**Area:** vision / pan-tilt / hardware smoke safety  
**Status:** resolved with guard

### Problem

The tiny pan-tilt smoke preview looked safe at the target level, but the saved calibration state showed:

- x = 0.0
- y = 80.0

The planned sequence first moves to center:

- X = 0
- Y = 0

This means execute mode could have caused a large movement before the tiny 0.25 degree tracking target command.

### Risk

The script name and requested target suggested a tiny movement, but the initial center command could be much larger if the physical pan-tilt was truly near Y=80.

This could create cable strain or collision risk.

### Fix applied

A center-state guard was added to the tiny smoke script.

Execute mode now refuses to run unless the saved calibration state is near center:

- abs(x) <= 0.5
- abs(y) <= 0.5

Preview mode still works.

### Result

The execute test correctly refused hardware movement with:

- Refusing execute because calibration state is not near center.
- Current state is X=0.0 Y=80.0.
- Run a safe manual center step first, then re-run preview.

### Follow-up rule

Before any tiny tracking smoke execute, confirm that both saved calibration state and physical pan-tilt position are near center.

If not, use a dedicated safe center recovery checklist/script first.

---

## Vision Runtime — pan-tilt did not move because UART pins were wired incorrectly

**Date:** 2026-05-05  
**Area:** vision / pan-tilt / Waveshare / GPIO UART  
**Status:** resolved

### Problem

The Waveshare pan-tilt scripts were sending commands successfully, but the pan-tilt did not move.

Observed command path:

- `/dev/serial0`
- `/dev/ttyAMA0`
- GPIO14 / TXD0
- GPIO15 / RXD0

The system configuration looked correct:

- `enable_uart=1`
- `/dev/serial0 -> ttyAMA0`
- `serial-getty` inactive
- user in `dialout`
- GPIO14 showed `TXD0`
- GPIO15 showed `RXD0`

Despite this, the hardware did not move.

### Root cause

The UART pins were wired incorrectly.

After correcting the physical pin wiring, the behaviour/emotion pan-tilt test worked.

### Correct wiring rule

For Raspberry Pi GPIO UART:

- Raspberry Pi physical pin 8 / GPIO14 TXD0 -> Waveshare RX
- Raspberry Pi physical pin 10 / GPIO15 RXD0 -> Waveshare TX
- Raspberry Pi GND -> Waveshare GND

TX/RX must be crossed.

Do not connect TX to TX and RX to RX.

### Result

After correcting the wiring, pan-tilt movement worked.

This confirms that the issue was physical wiring, not the NEXA Vision Runtime tracking pipeline or Python smoke scripts.

### Follow-up rule

Before debugging software movement logic, always verify:

- correct physical pins,
- crossed TX/RX,
- shared GND,
- pan-tilt power,
- `/dev/serial0` mapping,
- serial console disabled.

---

## Vision Runtime Sprint 10A — adapter runtime gate tests failed after partial patch

**Date:** 2026-05-05  
**Area:** vision / tracking / pan-tilt adapter / tests  
**Status:** resolved

### Problem

During Sprint 10A, the first patch partially succeeded but focused tests failed.

The failing tests were:

- tests/vision/unit/tracking/test_pan_tilt_execution_adapter.py::test_pan_tilt_adapter_prepares_dry_run_command_without_calling_backend
- tests/vision/unit/tracking/test_pan_tilt_execution_adapter.py::test_pan_tilt_adapter_blocks_even_when_config_requests_backend_execution

### Symptoms

The failures were:

- old test expected blocked_reason = dry_run_backend_command_gate
- new adapter returned blocked_reason = runtime_hardware_execution_gate
- old test expected status requested_backend_command_execution_enabled
- new status did not expose that compatibility field

### Root cause

Sprint 10A changed the pan-tilt adapter gate model from a single backend execution gate to a multi-gate hardware execution model.

The implementation was safe, but it broke old dry-run test expectations and removed a compatibility status key.

### Fix applied

The adapter was updated to preserve backward-compatible dry-run behaviour.

Changes:

- default dry-run still reports dry_run_backend_command_gate
- requested_backend_command_execution_enabled is exposed in adapter status
- new runtime hardware gates are still included
- effective_backend_command_execution_enabled remains false unless all explicit gates are enabled

### Result

Focused tests passed:

- tests/vision/unit/tracking/test_pan_tilt_execution_adapter.py
- tests/vision/unit/tracking/test_tracking_settings_contract.py
- tests/vision/unit/tracking/test_tracking_execution_readiness_validator.py
- tests/vision/unit/tracking/test_tracking_execution_readiness_check_command.py

The wider Sprint 10A test suite also passed.

### Follow-up rule

When adding new safety gates, preserve old dry-run result semantics unless there is a deliberate migration plan.

This keeps telemetry, tests, and runtime metadata stable while the hardware path evolves.


---

## Pan-tilt backend reports command execution but hardware does not move

**Date:** 2026-05-05  
**Area:** vision / pan-tilt / Waveshare serial runtime backend  
**Status:** resolved

### Symptoms

The runtime tracking path reported successful backend command execution:

- `backend_command_executed = true`
- `movement_executed = true`
- `serial_write_count > 0`

However, the Waveshare pan-tilt did not visibly move, even for a larger X target.

### What was ruled out

The issue was not caused by:

- UART wiring
- `/dev/serial0`
- power
- Waveshare controller failure
- pan-tilt mechanical failure

This was confirmed because the hardware emotion behavior smoke test moved the pan-tilt correctly.

### Root cause

The new `PanTiltService` runtime backend sent a shorter and faster command sequence than the working hardware smoke test.

The Waveshare controller accepted serial writes but did not physically respond reliably to the minimal runtime sequence.

### Fix

The runtime backend was updated to use a fuller Waveshare preparation sequence before target movement:

- stop
- steady off
- pan-tilt mode
- torque on
- hold current position
- target movement

The sequence now includes safer timing between commands.

### Validation

After the fix, a visible X-axis movement through `PanTiltService` moved the real pan-tilt hardware successfully.

### Lesson

For Waveshare pan-tilt runtime movement, successful serial writes are not enough to prove physical motion.

If the backend reports execution but hardware does not move, compare the runtime command sequence and timing against the known-good hardware smoke test before assuming wiring or power failure.

