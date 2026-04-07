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

```bash
python -m tests.test_voice_commands
```
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

```python
AttributeError: 'CoreAssistant' object has no attribute 'boot'


### Cause
The startup logic was accidentally pasted inside `__init__()` instead of being defined as a separate class method. As a result, the object executed startup behaviour during construction, but no actual `boot()` method existed.

### Fix
The boot logic was moved out of `__init__()` and restored as a separate method:

```python
def boot(self) -> None:
```
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