# Core Execution & Pressure Engine

## The Tick Loop
The Household Agent is not a reactive bot; it operates on a continuous "tick" cycle. Time passes regardless of whether the user speaks.
- **`chat.py`**: A CLI interface where hitting `<Enter>` triggers an idle tick, allowing the agent to "think" without input.
- **`server.py`**: A web server that provides an auto-tick loop (triggering `/api/tick` periodically) and handles live chat.

## Pressure Engine (`pressure_engine.py`)
At the center of the system is the pressure engine. It models the agent's internal state using four "buckets":
1. **Decompress**: Driven by `user_stress`. The urge to help the user relax.
2. **Contribute**: Driven by `open_task_load` and idle time. The urge to be useful.
3. **Learn**: Driven by `knowledge_gap`. The urge to research or ask questions.
4. **Connect**: Driven by `time_since_interaction`. The urge to bond or reach out.

### The Three Phases of a Tick
1. **Phase A (Charge)**: Raw signals from the environment (like stress or idle time) pour into the buckets. Buckets naturally decay (leak) over time.
2. **Phase B (Flow)**: Pressure flows between buckets along defined graph edges. For example, excess "Learn" pressure might flow into "Contribute", creating emergent behaviors.
3. **Phase C (Discharge)**: Any bucket that exceeds its threshold triggers an action. 

### Actions
When a bucket fires, it triggers one of three actions:
- **reach_out**: The agent proactively starts a conversation.
- **research**: The agent searches the web (read-only) for information, summarizing it into a "User Digest" and a "Journal Note".
- **internal_thought**: The agent logs a private thought to its internal journal without notifying the user.

### Model Backends
The engine abstracts the LLM provider via `call_model()`. It supports:
- **Ollama**: Default local backend.
- **Anthropic**: Cloud fallback.
- **llama-cpp-python**: Alternative local inference.
The engine includes a `DRY_RUN` mode which simulates actions (like web searches or reach-outs) without actually calling the LLM, allowing rapid testing of the pressure dynamics.
