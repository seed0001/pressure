# Interfaces, APIs, and Speech

`server.py` is the main interface layer. It serves the desktop dashboard, mobile
chat, backend APIs, browser-camera ingestion, and text-to-speech.

## Startup

Use `start.bat` or run `server.py` directly.

The launcher sets `LIVING_CONTAINER_NO_VENV_REDIRECT=1` and prefers the bundled
Codex Python runtime when available. This avoids the stale virtual environment
from the inherited project.

By default, the server uses HTTPS. If certificate files are missing, it creates
a local self-signed certificate under `certs/` for:

- `localhost`;
- `127.0.0.1`;
- the current LAN IP when it can be detected.

HTTPS matters for browser-device camera access over LAN.

## Core APIs

- `GET /api/state`: full state payload.
- `GET /api/graph`: compatibility knowledge graph.
- `GET /api/memory_field`: symbolic pressure memory.
- `GET /api/mycelial_field`: field memory, tokens, merge events, and context.
- `GET /api/metabolism`: ATP, fatigue, rest drive, and growth readiness.
- `GET /api/ecology`: ecology bridge state and pressure signals.
- `POST /api/chat`: user message.
- `POST /api/tick`: full pressure tick with action dispatch.
- `POST /api/signals`: manual signal updates.
- `POST /api/ecology_metrics`: feed internal ecology metrics.
- `POST /api/config`: update runtime config.
- `POST /api/tts`: generate speech audio.
- `POST /api/reset`: reset runtime state.
- `POST /api/clear_memory`: clear memory organs and compatibility graph.
- `POST /api/vision_frame`: browser-camera frame input.
- `POST /api/vision_state`: structured vision state input from external tools.

## State Payload

`GET /api/state` includes:

- current tick;
- pressure buckets and thresholds;
- raw signals;
- vision status;
- journals and outbox;
- analyzer context packet;
- primitive concept state;
- model status;
- graph summary/counts;
- symbolic pressure memory;
- mycelial field state;
- metabolism;
- ecology;
- messages;
- edge flow totals;
- config.

This endpoint is intentionally broad because the dashboard is diagnostic.

## Ecology Metrics Input

`POST /api/ecology_metrics` accepts JSON metrics from an internal ecology.

Example:

```json
{
  "epoch": 120,
  "high_order_entropy": 0.62,
  "unique_count": 240,
  "population": 1280,
  "territorial_dominance": 0.44
}
```

The ecology bridge converts this into pressure signals. It does not speak by
itself; it changes the organism's internal conditions.

## Dashboard

The desktop dashboard is served at `/`.

It is currently still partly inherited from the pressure project. It shows the
main pressure loop, graph, messages, internal thoughts, vision state, and runtime
configuration. Some new organs are exposed through APIs before they are fully
visualized in the UI.

## Mobile Chat

The mobile interface is served at `/mobile`.

It provides a lightweight chat surface, polls `/api/state`, and supports speech
playback on mobile browsers by unlocking audio after user interaction.

## Browser Camera

Browser-camera mode is the preferred presence path.

Use HTTPS for LAN camera capture. The UI can send frames to `/api/vision_frame`,
where the server processes them if OpenCV is available. If OpenCV is missing,
the app can still run; vision simply reports the unavailable state.

## Speech

The default speech path uses `edge_tts_speak.js`, called by `/api/tts`.

The server passes text and voice selection to Node.js. The script uses
`msedge-tts` and streams MP3 bytes back through stdout.

There is also a LuxTTS path in the inherited code. It attempts to initialize a
local clone voice and falls back to Edge TTS when unavailable.

## Dry Run

`--dry` keeps the organism ticking without live model/search calls. This is the
safest mode for testing pressure, memory, metabolism, startup, and UI behavior.
