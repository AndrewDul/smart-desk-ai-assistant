# NEXA Visual Shell

NEXA Visual Shell is the premium animated system interface for NEXA.

It is responsible for rendering NEXA's visual presence on the 8-inch DSI display:
a living particle cloud, eyes formation, face contour, speaking pulse, scanning mode,
desktop-docked mode, and fullscreen assistant mode.

The Visual Shell is not the assistant brain. It does not decide what NEXA should do.
It receives state commands from the Python runtime and renders the correct visual state.

## Initial states

- `IDLE_PARTICLE_CLOUD`
- `LISTENING_CLOUD`
- `THINKING_SWARM`
- `SPEAKING_PULSE`
- `SCANNING_EYES`
- `SHOW_SELF_EYES`
- `FACE_CONTOUR`
- `BORED_MICRO_ANIMATION`
- `DESKTOP_HIDDEN`
- `DESKTOP_DOCKED`
- `DESKTOP_RETURNING`
- `ERROR_DEGRADED`

## Architecture

Python side:

- `contracts/` defines stable state, command, and event models.
- `controller/` maps runtime events to visual shell commands.
- `transport/` sends messages to the renderer.
- `config/` stores display and animation defaults.

Godot side:

- `godot_app/` will contain the native animated renderer.
- The renderer will later receive commands from the Python runtime through local IPC/WebSocket.

## Design rule

The Visual Shell must remain modular. Animation logic, state mapping, transport, and runtime integration
must stay separated. No single file should become a large monolith.