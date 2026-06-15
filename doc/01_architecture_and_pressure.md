# Core Execution & Pressure Engine

## The Tick Loop
The Household Agent is not a reactive bot; it operates on a continuous "tick" cycle. Time passes regardless of whether the user speaks.
- **`chat.py`**: A CLI interface where hitting `<Enter>` triggers an idle tick, allowing the agent to "think" without input.
- **`server.py`**: A web server that provides an auto-tick loop (triggering `/api/tick` periodically) and handles live chat.

## Startup and Environment Execution
To ensure stability on Windows systems with multiple Python installations, the entry point in `server.py` detects if it is executed outside its target virtual environment. If so, it automatically restarts itself using the virtual environment interpreter (`venv/Scripts/python.exe`), where all OpenCV and NumPy dependencies reside. A double-clickable `start.bat` script is provided to automate launching the server in a persistent console window.

## Pressure Engine (`pressure_engine.py`)
At the center of the system is the pressure engine. It models the agent's internal state using multiple "buckets" (Decompress, Contribute, Learn, Connect, Curiosity, Focus, Clarify, Reflect, Bond, and Contemplate).
- **Decompress**: Driven by `user_stress`. The urge to help the user relax.
- **Contribute**: Driven by `open_task_load` and idle time. The urge to be useful.
- **Learn**: Driven by `knowledge_gap`. The urge to research or ask questions.
- **Connect**: Driven by `time_since_interaction`. The urge to bond or reach out.

### The Three Phases of a Tick
1. **Phase A (Charge)**: Raw signals from the environment (like stress or idle time) and visual perception observations pour into the buckets. Buckets naturally decay (leak) over time.
2. **Phase B (Flow)**: Pressure flows between buckets along defined graph edges. For example, excess "Learn" pressure might flow into "Contribute", creating emergent behaviors.
3. **Phase C (Discharge)**: Any bucket that exceeds its threshold triggers an action.

### Actions and Pressure-Based Pacing Friction (Speech Gravity)
When a bucket fires, it triggers one of three actions:
- **reach_out**: The agent proactively starts a conversation.
- **research**: The agent searches the web (read-only) for information, summarizing it into a "User Digest" and a "Journal Note".
- **internal_thought**: The agent logs a private thought to its internal journal without notifying the user.

Rather than relying on rigid rules, mutexes, or absolute cooldown timers, the pacing of the agent is controlled dynamically using **speech gravity and pressure friction**:
- **Speech Active Pressure**: While the text-to-speech output is playing, a friction cost is computed based on the remaining audio duration.
- **Listening Debt**: If the user has not yet had sufficient time to consume the response, a listening cost increases the threshold of competing outputs.
- **Overlap Penalty**: If the output audio channel is active, an overlap penalty of 1.2 is added to block interruptions.
- **Settling Pressure**: A temporary settling load is created by large responses, which decays naturally over ticks.
- **Effective Pressure Formula**: Competing actions are evaluated by deducting all active friction costs from the bucket's raw pressure:
  `effective_pressure = raw_pressure - speech_active_pressure - listening_debt - settling_pressure - overlap_penalty`
  An action will only trigger if this `effective_pressure` exceeds its normal threshold. This creates a natural physical gravity where the world gets heavier when the agent is speaking, postponing future research, reach-outs, and thoughts until the previous speech has finished and settled.
- **User Engagement Relief**: Whenever a user message is received, all communication-related pressure buckets (Connect, Decompress, Bond, Reflect, Curiosity, Focus, Clarify) are immediately reduced by `60%` (multiplied by `0.4`), reflecting that active engagement immediately decompresses the urge to reach out.
- **Enhanced Decompression**: Firing an action relieves `85%` of the bucket's pressure (`RELEASE_FRACTION = 0.85`), preventing immediate re-triggering.
- **Concurrent Action Lockout**: At most one action (reach-out, research, or thought) is allowed to fire per tick (`fired_any` lockout flag). Any other candidate actions that cross their thresholds in the same tick are safely blocked and logged under `"concurrent_action_lockout"`, preventing concurrent action cascades.
- **Expression Exhaustion**: When a `reach_out` action (speaking) successfully fires, all other communication-related buckets are immediately decompressed by `50%` (`updated[b] *= 0.5`). This models the physical energy cost of expression, preventing consecutive-tick machine-gun speaking spikes as speech gravity decays.
- **Unstructured Presence Suppression**: When the conversation analyzer detects a relaxed, open-ended state without a specific goal (signal `"unstructured_presence"` is high), it suppresses the charging drive of objective-seeking buckets (`Curiosity` and `Clarify` are dampened by up to 85%, and `Learn` by up to 70%). This allows the agent to comfortably "hang out" without feeling pressured to resolve topics or perform research tasks.

### Model Backends
The engine abstracts the LLM provider via `call_model()`. It supports Ollama (local default), Anthropic (cloud), and llama-cpp-python (local alternative). The engine includes a `DRY_RUN` mode which simulates actions (like web searches or reach-outs) without actually calling the LLM, allowing rapid testing of the pressure dynamics.
