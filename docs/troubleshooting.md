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