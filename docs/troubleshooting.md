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