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

