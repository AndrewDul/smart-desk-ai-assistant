# Test Notes - 31 March 2026

## Core assistant checkpoint
Today I completed the first running version of the Smart Desk AI Assistant core.

## Confirmed working
- project structure created
- GitHub repository created and linked
- assistant starts correctly
- voice output works
- help command works
- memory save works
- memory recall works
- reminder creation works
- focus timer works
- status command works
- stop timer works

## Notes
- current input is text-based fallback
- OLED integration still to do
- microphone quality still needs improvement



# Test Notes

## Date
2026-04-01

## Current project stage
Stage 1 - stationary assistant core without camera

---

## 1. Main progress confirmed

The project now has a working early prototype of the Smart Desk AI Assistant core.

The following parts were completed or confirmed working:

- Raspberry Pi 5 setup completed
- Raspberry Pi OS installed on 128 GB microSD card
- Raspberry Pi connected to Wi-Fi
- system updated
- active cooler installed and tested
- temperature behaviour checked manually under heavier usage
- speaker connected and tested
- USB microphone connected and tested
- OLED connected and working
- project structure created
- assistant starts correctly
- assistant shuts down correctly
- voice output works
- voice recognition works in a basic offline form using Vosk
- help command works
- status command works
- memory save works
- memory recall works
- reminder creation works
- reminder trigger loop works
- focus timer works
- break timer works
- stop timer works
- OLED menu/status/help style screens work
- OLED eye animation works in idle mode

---

## 2. Hardware testing notes

### Cooling
The active cooler worked correctly.

Manual test method:
- checked Raspberry Pi temperature from terminal
- opened multiple browser tabs
- opened video content
- watched whether temperature increased significantly

Result:
- Raspberry Pi stayed stable
- cooling worked correctly
- temperature remained under control during normal test usage

### Speaker
Speaker output was confirmed working.

### Microphone
The microphone worked, but quality was not ideal.

Observed issue:
- microphone captured too much background noise
- voice command recognition sometimes required repeated attempts

Conclusion:
- microphone is usable for current development
- a better microphone or USB headset should be considered later

### OLED
OLED output now works.

Confirmed:
- simple display output works
- menu screens work
- helper/status/reminder screens work
- animated eye mode works
- display can switch between animation and timed information screens

---

## 3. Voice command notes

Basic voice commands were tested successfully.

Commands confirmed in current version:
- show help
- show status
- show memory
- show reminders
- show menu
- stop timer
- exit assistant

Memory examples:
- remember keys equals drawer
- recall keys

Timer examples:
- focus 1
- break 1

Reminder example:
- remind me in 10 seconds to stretch

---

## 4. Current limitations

Current known limitations:
- microphone quality is still weak
- recognition reliability is not perfect
- some commands may need to be repeated
- command vocabulary is still limited
- settings file exists and is now being integrated into runtime control
- camera features are not implemented yet
- mobility is not implemented yet
- dashboard is not implemented yet

---

## 5. Current conclusion

The assistant already functions as a real early stage 1 prototype.

It currently supports:
- voice input
- voice output
- memory
- reminders
- focus/break timing
- OLED feedback
- OLED animation
- logging
- boot/shutdown flow

This is a valid working foundation for the next project stage.


# Hardware Test Notes

## Overview

After replacing my original hardware, I wrote and ran several tests to check the new LCD and new microphone.

These tests helped me separate hardware problems from software problems.

---

## New Hardware Tested

### LCD
**Waveshare 2inch LCD Module**
- ST7789V / ST7789VW
- 240 x 320
- SPI
- colour LCD

### Microphone
**Seeed Studio ReSpeaker XVF3800 USB 4-Mic Array**
- USB microphone array
- used as microphone only
- separate USB speaker kept for output

---

## Microphone Tests

### 1. Device detection test
I used:

`arecord -l`

### Result
The system detected the new microphone as:
- **card 2**
- **device 0**
- **reSpeaker XVF3800 4-Mic Array**

This confirmed that the Raspberry Pi could see the microphone correctly.

---

### 2. Recording test
I used:
- `arecord -D plughw:2,0 ...`

At first I accidentally used the wrong card number, so the test failed.
After correcting the card number, the recording command worked.

### Result
The microphone recorded successfully.

---

### 3. Real quality check
After testing it properly, I confirmed that:
- the input was very clean
- there was almost no noise
- the microphone quality was much better than my previous one

### Final microphone result
**PASS**

The ReSpeaker XVF3800 works very well and became my main voice input device.

---

## LCD Tests

### 1. Initial LCD test with old project display path
I tried to use the new LCD through the older project display flow.

### Result
The screen did not work correctly.

Problems included:
- noise on one side
- flashing area
- only part of the image visible

### Conclusion
The LCD was not working correctly with that software path.

---

### 2. `luma.lcd` based test
I tested the display through a `luma.lcd` style path.

### Result
The screen partially responded, but the output was still corrupted.

### Conclusion
This backend was not stable for this panel.

---

### 3. `st7789_manual_smoke.py`
I created a manual ST7789 smoke test.

### Purpose
To check whether a different ST7789-based path could drive the LCD correctly.

### Result
The display still did not behave correctly.
The image was unstable or incomplete.

### Conclusion
A generic ST7789 path was still not enough.

---

### 4. Official Waveshare Python demo
I downloaded and ran the official Waveshare Python demo for the 2inch LCD.

### Result
This was the most important LCD test.

The display showed the image correctly.

### Conclusion
This proved:
- the LCD hardware was correct
- the wiring was correct
- SPI was working
- the main problem was software integration, not the hardware itself

### Final result
**PASS**

This was the strongest successful LCD test.

---

### 5. `waveshare_direct_overlay_test.py`
I created a direct vendor-based LCD test.

### Purpose
To bypass the older project display wrapper and test drawing more directly with the Waveshare path.

### Result
This helped me experiment with:
- custom overlays
- eye graphics
- frame rendering
- orientation handling

The behaviour was mixed and helped show that runtime integration still needed more work.

### Conclusion
This test was useful for diagnosis, even when the result was not fully stable.

---

### 6. `scripts/test_oled.py`
I reused this script as a display test entry point, even though the file name still referred to OLED.

### Purpose
To test the current project display runtime with the new LCD.

### Result
The test confirmed that the current runtime still had display update issues.
In some versions the screen stayed dark, or only showed a small part of the eyes for a short time.

### Conclusion
The file remained useful as a quick entry test, but the runtime needed more adjustment.

---

### 7. `manual_tests/oled_smoke.py`
I also reused this manual display test file.

### Purpose
To test overlay and eye display transitions using the current project runtime.

### Result
It helped me check:
- whether overlay text was shown
- whether eye frames appeared
- whether the display stayed stable after transitions

This was useful for manual checking, even though the LCD path still needed work.

---

## Overall Test Summary

### Successful tests
- ReSpeaker detection
- ReSpeaker recording test
- real microphone quality check
- official Waveshare vendor LCD demo

### Useful diagnostic tests
- `st7789_manual_smoke.py`
- `waveshare_direct_overlay_test.py`
- `scripts/test_oled.py`
- `manual_tests/oled_smoke.py`

### Main outcome
The new microphone upgrade was fully successful.

The new LCD hardware was also proven to be correct, but integrating it cleanly into my own runtime display code required more work than expected.

The official Waveshare vendor demo was the most reliable LCD test result.

## Test notes - bilingual voice assistant improvements

During this stage I tested both the software logic and the real voice input behaviour.

### Automated tests

After the refactoring and modularisation work, I updated and ran the test suite.

Final result:

- all tests passed
- the assistant core stayed stable after the changes
- timer, focus, break, reminders, memory, and parsing logic were all working in the test environment

This gave me confidence that the internal logic was still correct after restructuring the project.

### Manual voice tests

I also carried out real manual tests with the reSpeaker microphone.

At first the results were poor. The assistant had serious problems with Polish commands, and sometimes it mixed Polish and English. Some short Polish phrases were misunderstood badly.

I then investigated the microphone and audio setup:

- I checked the available audio devices
- I confirmed that the correct microphone was the reSpeaker XVF3800 array
- I confirmed that the correct input device index was `1`
- I confirmed that `16000` was the correct sample rate
- I checked raw signal values and confirmed that the microphone was receiving audio properly

### Speech model tests

I first tested the assistant with the Whisper base model.

Result:
- not good enough for my target
- too weak for short Polish commands
- too unreliable for a premium bilingual assistant

I then switched from `base` to `small`.

Result:
- clear improvement immediately
- much better recognition of both English and Polish
- main commands became much more reliable
- the assistant now understands commands much better overall

### Current practical result

What is now much better:

- English and Polish command recognition
- command reliability
- use of the correct microphone
- timer / focus / break flow
- startup and help flow
- real usability

What still needs more work:

- response language consistency
- sometimes the assistant still replies in the wrong language
- some polish / english reply switching still feels inconsistent

### Overall conclusion

This stage was a major improvement.

The assistant is now in a much better state than before. It understands the main commands much more reliably and the bilingual recognition problem is much smaller than it was at the beginning of this work.

It is still not perfect yet, but this was a big step forward.