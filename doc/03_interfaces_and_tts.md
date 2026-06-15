# Interfaces, APIs, and TTS

The Household Agent relies on `server.py` to serve both the web interfaces and the backend APIs.

## 1. Backend API (`server.py`)
The server is a standard Python `ThreadingHTTPServer` that wraps the `pressure_engine.py` state.
- `GET /api/state`: Returns a massive JSON payload containing the current tick, all bucket pressures, graph statistics, the context packet, the internal journal, and tentative concepts.
- `POST /api/chat`: Handles user messages. It immediately infers simple text stress, updates the context, and synchronously blocks to return a passive LLM reply.
- `POST /api/tick`: Advances the engine manually (used by the frontend auto-tick).
- `POST /api/tts`: Converts text to speech using Microsoft Edge's TTS service.
- `POST /api/config`: Updates live settings (e.g., `DRY_RUN`, focus subject, model).
- `POST /api/toggle_cam`: Toggles the background camera thread execution on/off.
- `POST /api/vision_state`: Accepts structured JSON visual state updates from remote vision clients.

## 2. User Interfaces

### Main Dashboard (Desktop)
Served at `/`. This is a complex diagnostic view.
- Visualizes bucket pressures with color-coded progress bars.
- Renders the knowledge graph dynamically on a 2D canvas.
- Shows internal thoughts, the analyzer's output, and edge flow totals.
- Maintains an auto-tick loop (`setInterval`) that drives the system forward.
- **Camera Toggle**: Features a "Cam On" / "Cam Off" button in the top bar to enable or disable the ambient vision system.

### Mobile Chat UI
Served at `/mobile`. A lightweight, responsive chat interface tailored for phones.
- Polls `/api/state` every 1.5 seconds.
- Uses a `lastMsgCount` check to only re-render the DOM when new messages arrive.
- **Audio Autoplay Fix**: Mobile browsers block asynchronous audio. To bypass this, the UI creates a blank `Audio` object the moment the user taps "Voice on" or "Send". When the TTS audio arrives, this unlocked object is recycled (`currentAudio.src = url`), allowing the agent to speak natively on iOS and Android.

## 3. Remote System Camera Configuration
If the server is running on a machine without a camera or if you want to use a camera on a remote machine:
- **CLI Flag `--no-cam`**: Run the server with `--no-cam` (or double-click `start.bat --no-cam`) to completely disable starting the local camera thread.
- **Remote client script (`remote_vision_client.py`)**: Run this script on the remote system with the webcam attached. It performs the OpenCV Haar face cascades, motion levels, scene changes, and brightness estimations locally, and pushes the lightweight JSON state over the network to the server's `/api/vision_state` endpoint.

## 4. Text-to-Speech (`edge_tts_speak.js`)
Because Python libraries for Edge TTS can be unstable, the system delegates TTS to a Node.js script.
- Python's `/api/tts` calls `subprocess.run(["node", "edge_tts_speak.js", text])`.
- The JS script uses the `msedge-tts` NPM package to stream 24kHz MP3 audio from Microsoft's servers.
- The script pipes the binary audio to `stdout` and strictly calls `process.exit(0)` when finished. This explicit exit prevents the underlying WebSocket connection from keeping the Node process alive and hanging the Python server.
