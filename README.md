# Living Conversational Container

The Living Conversational Container is a merged experimental companion runtime.
It is built from the `pressure` conversation engine, the mycelial field/token
memory ideas from `TheMycelialCortex`, and an ecology bridge intended to receive
signals from `computational-life`.

The goal is not to make a chatbot with a dramatic prompt. The goal is to give
the system a small computational body: pressure, memory, metabolism, perception,
and ecology all evolving over time.

## What It Is

This project treats conversation as the visible surface of an internal organism.
The main runtime is still Python, but the architecture is no longer only a
request-response assistant.

- `pressure_engine.py` is the spine. It runs pressure buckets through charge,
  flow, and discharge on every tick.
- `pressure_memory.py` is the symbolic pressure memory. First-contact material
  enters as volatile pressure and only becomes projectable after circulation.
- `mycelial_field.py` is the vector/token memory organ. It recalls, grows,
  consolidates, emits ordered sparse tokens, and merges redundant fragments.
- `metabolism.py` tracks ATP, fatigue, rest drive, and recall gain. Exhaustion
  gates memory growth and can block expensive research actions.
- `ecology_bridge.py` maps computational-life metrics into pressure signals.
  Entropy shift, diversity, lineage flux, stagnation, and novelty become part
  of the system's internal weather.
- `server.py` serves the dashboard, mobile chat, state APIs, vision input, TTS,
  and the tick loop.

## Current Status

Implemented:

- Continuous pressure-driven tick loop.
- Browser-camera presence path with optional local-camera fallback.
- Symbolic pressure memory.
- Mycelial field memory with ordered/chiral token emission.
- Merge-on-consolidate for redundant mycelial memory fragments.
- ATP/fatigue metabolism.
- Metabolic gating for growth and research.
- Ecology metrics ingestion API.
- HTTPS auto-certificate generation for local/LAN browser-camera use.
- Dry-run mode for startup and pressure testing without model/search calls.

Not complete yet:

- A dedicated Rust exporter for `computational-life` metrics.
- Full ordered token federation between multiple running instances.
- UI panels for every new internal organ.
- A finalized public identity/personality layer.

## Quick Start

Double-click:

```bat
start.bat
```

Or run from PowerShell:

```powershell
cd "C:\Users\aztre\Desktop\New folder (31)\living-container"
$env:LIVING_CONTAINER_NO_VENV_REDIRECT='1'
& "C:\Users\aztre\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" server.py --dry --no-cam
```

The server prints local and LAN URLs. By default it serves HTTPS and will create
`certs/server.crt` and `certs/server.key` if they are missing.

Useful flags:

- `--dry`: Run without live model/search calls.
- `--live`: Enable live model/search behavior.
- `--http`: Serve plain HTTP instead of HTTPS.
- `--no-cam`: Do not start a local camera thread.
- `--local-cam`: Use a camera attached to the server machine.
- `--model <name>`: Select an Ollama model.

## Main APIs

- `GET /api/state`: Full runtime state, including pressure, memory, metabolism,
  ecology, graph, vision, messages, and config.
- `GET /api/mycelial_field`: Mycelial memory state and recent token stream.
- `GET /api/metabolism`: ATP, fatigue, rest drive, and growth/readiness state.
- `GET /api/ecology`: Current ecology bridge state.
- `POST /api/ecology_metrics`: Feed computational-life-style metrics into the
  pressure spine.
- `POST /api/chat`: Send a user message.
- `POST /api/tick`: Advance the organism by one tick.
- `POST /api/vision_frame`: Send a browser-camera frame.
- `POST /api/tts`: Generate speech audio.

Example ecology metrics payload:

```json
{
  "epoch": 120,
  "high_order_entropy": 0.62,
  "unique_count": 240,
  "population": 1280,
  "territorial_dominance": 0.44
}
```

## Verification

Run the focused checks:

```powershell
& "C:\Users\aztre\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scratch\test_living_container.py
& "C:\Users\aztre\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scratch\test_pressure_memory.py
```

Expected output:

```text
living container OK
pressure memory OK
```

## Design Rule

If a behavior can be expressed as pressure, resonance, metabolic cost, presence,
or ecology signal, prefer that over a special-case rule. The system should feel
alive because its internal state has consequences, not because a prompt tells it
to imitate aliveness.
