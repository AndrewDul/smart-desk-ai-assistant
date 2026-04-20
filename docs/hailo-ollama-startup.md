# Hailo Ollama Startup Guide

## Purpose

This file explains the quickest way to start the local LLM backend on Raspberry Pi 5 with AI HAT+ 2 and verify that the HAT-based LLM path is working.

This guide assumes the Hailo software stack is already installed.

---

## What I am starting

For local LLM inference on AI HAT+ 2, I start:

- the `hailo-ollama` server in one terminal
- model management and chat requests from a second terminal

The server exposes a local API on port `8000`.

---

## Quick start

### Terminal 1 — start the Hailo LLM server

```bash
hailo-ollama
```
Expected result:

the process stays running
the server listens locally on port 8000

Do not close this terminal while testing the LLM.

### Terminal 2 — list available Hailo models

```bash
curl --silent http://localhost:8000/hailo/v1/list
```
This returns the list of models supported by the current Hailo setup.

Terminal 2 — pull a model

Example:

```bash
curl --silent http://localhost:8000/api/pull \
  -H 'Content-Type: application/json' \
  -d '{ "model": "qwen2:1.5b", "stream": true }'
```
Notes:

use "model", not "name"
keep "stream": true
the first pull can take a while

### Terminal 2 — send a chat request

Example:
```bash
curl --silent http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2:1.5b",
    "messages": [
      { "role": "user", "content": "Explain what a black hole is in simple terms." }
    ]
  }'
  ```
  If the model is loaded correctly, I should get a local response from the Hailo-backed LLM server.

### Useful checks

Check whether the Hailo device is visible
```bash
hailortcli fw-control identify
```

If the device is detected correctly, I should see Hailo hardware information.

Check whether the hailo-ollama command exists
```bash
which hailo-ollama
```

If nothing is returned, the Hailo LLM stack is not installed correctly or the binary is not on the current PATH.

Check whether the local API port responds
```bash
curl --silent http://localhost:8000/hailo/v1/list
```

If this does not return anything useful while hailo-ollama is running, the server did not start correctly.

### Recommended test flow for NeXa

When I want to verify the HAT LLM path before running NeXa benchmarks, I use this order:

### 1.Start the server:
```bash
hailo-ollama
```

### 2. In another terminal, list models:
```bash
curl --silent http://localhost:8000/hailo/v1/list
```

### 3.Pull a small supported model:
```bash
curl --silent http://localhost:8000/api/pull \
  -H 'Content-Type: application/json' \
  -d '{ "model": "qwen2:1.5b", "stream": true }'
  ```

### 4.Run one chat sanity test:
```bash
curl --silent http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2:1.5b",
    "messages": [
      { "role": "user", "content": "Say hello in one short sentence." }
    ]
  }'
  ```

### Only after that start NeXa voice / LLM validation runs.
If hailo-ollama is not recognised

If I get command not found, I check:
```bash
which hailo-ollama
```
Then I verify:

the Hailo GenAI package was actually installed
the shell session sees the binary on PATH
the installation completed without errors

If needed, I reinstall the Hailo LLM package and then open a new terminal session.

### If NeXa still does not produce LLM benchmark samples

If Hailo chat works from curl, but NeXa still does not generate llm samples in benchmark validation, the problem is not HAT startup anymore.

Then I inspect:

routing to LLM vs skill path
response_reply_source
dialogue_source
llm_source
llm_first_chunk_ms
response_live_streaming

In that case, the backend is alive, but the NeXa runtime is not classifying or delivering the turn as a real LLM dialogue turn.

Practical reminder
keep hailo-ollama running in its own terminal during testing
use a second terminal for curl commands
the first response after model load can be slower
use small supported models first for sanity checks