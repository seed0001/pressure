# Analysis, Memory, and Vision

This section covers how the agent perceives the world, reasons about it, and remembers it across sessions.

## 1. Conversation Analyzer (`conversation_analyzer.py`)
Instead of simply passing raw text to the pressure engine, the agent uses an LLM-powered analyzer to convert chat history and ambient environment context into a structured **Context Packet**.
The packet extracts:
- `active_topics`: Recurring subjects in the conversation.
- `emotional_charge`: Tones like grief, frustration, trust.
- `unresolved_openings`: Dangling threads or unanswered questions.
- `curiosity_targets`: Things the agent wants to ask about.
- `relationship_state`: Trajectories of trust and tension.
- `conversation_depth`: A 0.0 to 1.0 score of how deep the talk is.

This packet is translated into numeric signals (e.g., high tension + unresolved openings -> `knowledge_gap` and `user_stress` spikes), which feed into the Pressure Engine.

## 2. Knowledge Graph (`knowledge_graph.py`)
The agent's long-term memory is a directed graph of Nodes and Edges.
- **Nodes**: Represent concepts, people, or objects (e.g., "divorce", "Alabama"). Each node holds a list of plain-English facts and a confidence score.
- **Edges**: Represent relationships between nodes (e.g., "User" -> "lives in" -> "Alabama").

The graph is updated by the LLM during conversation analysis or after web research. Instead of keyword-based retrieval, the agent performs a semantic similarity search using vector embeddings over the graph's nodes and facts to inject the most relevant nodes and relationships into the prompt.

## 3. Vector Embeddings and Episodic Memory (`memory_manager.py`)
To prevent the agent from losing track of conversation history and key facts, it integrates a multi-layer semantic memory system:
- **Ollama Vector Embeddings**: The agent attempts to query a local Ollama service (`/api/embed` or `/api/embeddings` targeting a model like `llama3.2`) to compute high-dimensional semantic vector embeddings.
- **Deterministic Hash-Vector Fallback**: If Ollama is offline or doesn't support embedding APIs, the system falls back to a deterministic 128-dimensional pseudo-random character-hash distribution based on a NumPy random state. This guarantees similarity computations continue working in any offline/development state.
- **Episodic Memory**: Every conversation exchange (the user message and agent response) is stored as a formatted episodic dialogue turn in `data/episodic_memory.json` along with its computed embedding vector.
- **Semantic Search**:
  - **Graph Semantic Search**: Rather than matching keywords, the agent retrieves relevant context by comparing the query's embedding vector against the embeddings of both knowledge graph node labels and their associated facts using cosine similarity.
  - **Episodic Semantic Search**: The agent queries past episodic dialogue history by comparing the user input's embedding against the cached episode vector embeddings, injecting the top matching dialogue turns directly into the prompt context.

## 4. Primitive Concept Engine (`primitive_concept_engine.py`)
This layer sits *below* the LLM. It detects patterns purely through structural observation.
Every tick, it captures a `StateSnapshot` (graph size, pressure values, active topics). It compares snapshots to detect "gaps" (e.g., topics that keep appearing without being resolved into the knowledge graph).
When a gap persists, it generates "Concept Pressure". If this pressure crosses a threshold, the engine aggregates the facts and asks the LLM to name a **Tentative Concept**.
Tentative concepts track `support` and `contradiction` over time. If they prove stable, they graduate to permanent nodes in the knowledge graph. This allows the system to learn structurally before it understands semantically.

## 5. Vision Sensor Layer (`vision_sensor.py`)
The vision sensor layer provides the agent with ambient perception of its physical surroundings.
- **Continuous Ambient Detection**: A background daemon thread captures frames at ~10 FPS. It computes human/face presence (using Haar cascades), motion level (using frame-by-frame pixel differences), scene changes, average brightness, and camera obstructions.
- **Cognitive Integration**: These raw readings are converted into a descriptive natural-English text block (e.g., `[Visual Perception: A person is present and paying attention to you.]`). This context block is injected directly into the LLM prompts when the agent chats, thinks, or reaches out.
- **Agent Identity**: The system-level prompt includes visual sensing capabilities, allowing the agent to naturally comment on visual changes (such as someone entering/leaving the room, moving, or blocking the camera) during interaction.

