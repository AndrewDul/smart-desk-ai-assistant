# NeXa Performance Targets

Ranked bottleneck list (Part F) with timing budgets (Part G).
Sources: `TurnBenchmarkService` telemetry, `turn_timeline.py` events,
`_last_response_delivery_snapshot`, and code-audit observations.

---

## Bottleneck Ranking (highest product impact first)

### #1 — LLM first token latency (highest impact)

| | |
|---|---|
| **What it is** | Time from route resolved → first token arrives from llama-server / hailo-ollama |
| **Where measured** | `first_token_latency_ms` in `_last_response_delivery_snapshot` and `llm_first_chunk_ms` in `TurnBenchmarkService.finish_turn()` |
| **Typical observed range** | 350–1 200 ms (depends on model, quantisation, RPi thermal throttle) |
| **Target** | **≤ 500 ms** (`first_token_latency_ms`); ≤ 400 ms with Qwen2.5-1.5B Q4 warm |
| **Fast-first mitigation** | `_split_fast_first_stream_chunk()` releases at clause boundary (≥ 36 chars) so TTS starts before sentence is complete; target: speech starts ≤ 800 ms after route |
| **Safe to optimise now** | Yes — keep model loaded (warmup_backend_if_enabled), reduce `stream_sentence_min_chars` cautiously |
| **Risk** | Low; model swap requires manual validation |

---

### #2 — FasterWhisper STT latency (fast-line commands blocked here)

| | |
|---|---|
| **What it is** | Time from audio capture end → transcript delivered for FasterWhisper path |
| **Where measured** | `listen_to_speech_ms` in benchmark sample; `stt_latency_ms` |
| **Typical observed range** | 400–900 ms on RPi 5 (depends on audio length, model size) |
| **Target** | **≤ 500 ms** for `listen_to_speech_ms` on `small.en` / `small` model |
| **Fast-first mitigation** | Vosk pre-Whisper fast path (`voice_engine_v2_candidate_accepted`) bypasses FasterWhisper entirely for known commands; target: 0 ms for fast-line commands |
| **Safe to optimise now** | Yes — Vosk pre-Whisper already deployed; verify `voice_engine_v2_candidate_accepted=true` in Diagnostics for known commands |
| **Risk** | Low; Vosk path is already tested |

---

### #3 — Wake / VAD detection lag

| | |
|---|---|
| **What it is** | Time from user finishes speaking → wake gate fires |
| **Where measured** | `wake_to_listen_ms` in benchmark sample |
| **Typical observed range** | 30–150 ms |
| **Target** | **≤ 80 ms** (`wake_to_listen_ms`) |
| **Notes** | reSpeaker mic + silero VAD; already fast. End-silence window configuration is the main lever |
| **Safe to optimise now** | Yes — tune `capture_end_silence_seconds` in settings |
| **Risk** | Low; shorter silence window risks cutting speech |

---

### #4 — TTS first audio (response perceived latency)

| | |
|---|---|
| **What it is** | Time from route resolved → first spoken audio byte |
| **Where measured** | `response_first_audio_ms`, `route_to_first_audio_ms` in benchmark sample; `first_audio_ms` in `_last_response_delivery_snapshot` |
| **Typical observed range** | 400–1 500 ms (LLM path); 100–300 ms (fast-line) |
| **Target** | **≤ 300 ms** for fast-line (`route_to_first_audio_ms`); **≤ 900 ms** for LLM first spoken chunk |
| **Piper daemon path** | In-process ONNX keeps model loaded; first synthesis typically 60–120 ms for a short chunk |
| **TTS cache** | Action fast profile uses `/dev/shm/nexa_tts`; repeated short phrases (time, greetings) should hit cache |
| **Safe to optimise now** | Yes — ensure `action_fast` TTS profile is used for fast-line responses |
| **Risk** | Low |

---

### #5 — Diagnostics `turn_on()` synchronous latency

| | |
|---|---|
| **What it is** | `FeedbackLane.turn_on()` blocks on camera `start()` (libcamera init) and `_publish_status_snapshot()` before returning |
| **Where measured** | `[diagnostics-latency]` log line when added; observed as libcamera init block in stdout before "DIAGNOSTICS" |
| **Typical observed range** | 60–300 ms (camera init dominates) |
| **Target** | **≤ 20 ms** for `turn_on()` to return; camera and snapshot moved to background |
| **Fix** | See plan file `memoized-conjuring-hellman.md` Part B — defer `cam.start()` to daemon thread; remove synchronous `_publish_status_snapshot()` call |
| **Safe to optimise now** | Yes — FeedbackVisionStreamer already resilient to `latest_frame()=None` |
| **Risk** | Low |

---

### #6 — `_publish_status_snapshot()` build time

| | |
|---|---|
| **What it is** | Snapshot builder iterates all 11 sections including HTTP calls to LLM `describe_backend()`, filesystem `rglob()` for tests section, hardware battery/temperature reads |
| **Where measured** | Not directly; contributes to diagnostics `turn_on()` latency and status-loop period |
| **Typical observed range** | 50–200 ms per build |
| **Target** | Background loop only; never on the response critical path |
| **Notes** | `_status_loop` thread calls `_publish_status_snapshot()` on its own schedule — the synchronous call in `turn_on()` is the only critical-path exposure |
| **Safe to optimise now** | Yes — removing it from `turn_on()` is the fix (see #5) |
| **Risk** | Low |

---

### #7 — Speech-to-route routing latency

| | |
|---|---|
| **What it is** | Time from transcript ready → route decision emitted |
| **Where measured** | `speech_to_route_ms` in benchmark sample |
| **Typical observed range** | 5–30 ms |
| **Target** | **≤ 20 ms** |
| **Notes** | FastCommandLane `classify()` is synchronous and deterministic; very fast. LLM routing context injection adds ~5 ms |
| **Safe to optimise now** | Already fast; monitor only |
| **Risk** | N/A |

---

### #8 — LLM total generation / streaming time

| | |
|---|---|
| **What it is** | Total time to generate and stream all LLM response chunks |
| **Where measured** | `llm_total_ms` and `response_total_ms` in benchmark sample |
| **Typical observed range** | 2 000–8 000 ms for 3–5 sentence replies |
| **Target** | No hard cap — streaming mitigates perceived latency; first chunk target is #1 above |
| **Notes** | `stream_sentence_soft_max_chars=120` limits chunk size; `max_sentences` per `_stream_server_chunks` call is configurable |
| **Safe to optimise now** | Monitor; reduce `max_sentences` for shorter contexts |
| **Risk** | Low |

---

### #9 — Camera / vision startup (background, only when Diagnostics open)

| | |
|---|---|
| **What it is** | libcamera / Picamera2 initialisation time; blocks `turn_on()` today |
| **Where measured** | Stdout libcamera init block; `camera_ms` in benchmark when available |
| **Typical observed range** | 200–600 ms |
| **Target** | Zero impact on spoken response latency — fully deferred to daemon thread |
| **Fix** | Part B of plan file |
| **Safe to optimise now** | Yes |
| **Risk** | Low — vision section gracefully shows empty when frame not yet ready |

---

### #10 — Visual Shell TCP send / Godot render visible

| | |
|---|---|
| **What it is** | Time from snapshot built → Godot receives payload → UI redraws |
| **Where measured** | `visual_shell_ms` in `_last_response_delivery_snapshot` when exposed |
| **Typical observed range** | 5–30 ms (TCP loopback); Godot scene update on next frame (~16 ms at 60 fps) |
| **Target** | **≤ 50 ms** from snapshot ready to Godot render visible |
| **Notes** | Already fast; not on the audio critical path |
| **Safe to optimise now** | Monitor only |
| **Risk** | N/A |

---

## Timing Budget Summary

| Stage | Budget | Measured field |
|---|---|---|
| Wake to listen | ≤ 80 ms | `wake_to_listen_ms` |
| STT (Vosk fast path) | 0 ms (bypassed) | `voice_engine_v2_candidate_accepted` |
| STT (FasterWhisper) | ≤ 500 ms | `listen_to_speech_ms` |
| Speech to route | ≤ 20 ms | `speech_to_route_ms` |
| Route to `turn_on()` return | ≤ 20 ms | `[diagnostics-latency]` log |
| LLM first token | ≤ 500 ms | `first_token_latency_ms` |
| LLM first speakable chunk | ≤ 700 ms | `first_speakable_chunk_latency_ms` |
| TTS first audio (fast-line) | ≤ 300 ms | `route_to_first_audio_ms` |
| TTS first audio (LLM path) | ≤ 900 ms | `response_first_audio_ms` |
| Full turn (fast-line) | ≤ 800 ms | `total_turn_ms` |
| Full turn (LLM) | ≤ 4 000 ms | `total_turn_ms` |

---

## Diagnostics Dashboard Coverage

The Performance section of the Feedback Center displays all key latency fields
sourced from `_last_response_delivery_snapshot` and `TurnBenchmarkService`:

| Label | Source field |
|---|---|
| `first_token_latency_ms` | `response_snapshot["first_token_latency_ms"]` |
| `first_speakable_chunk_latency_ms` | `response_snapshot["first_speakable_chunk_latency_ms"]` |
| `TTS first audio` | `response_snapshot["first_audio_ms"]` |
| `route_to_first_audio` | `latest_sample["route_to_first_audio_ms"]` |
| `total_action_ms` | `latest_sample["total_turn_ms"]` |
| `Vosk candidate accepted` | `latest_sample["voice_engine_v2_candidate_accepted"]` |
| `FasterWhisper prevented` | `latest_sample["faster_whisper_prevented"]` |
| `Event: STT / Listen to speech` | `latest_sample["listen_to_speech_ms"]` |
| `Slow op: Total turn` | `latest_sample["total_turn_ms"]` |

All fields have test coverage in
`tests/presentation/visual_shell/test_feedback_center_snapshot.py`.
