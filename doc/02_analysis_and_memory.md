# Analysis, Memory, and Primitive Concepts

This section covers how the agent perceives the world and remembers it across sessions.

## 1. Conversation Analyzer (`conversation_analyzer.py`)
Instead of simply passing raw text to the pressure engine, the agent uses an LLM-powered analyzer to convert chat history into a structured **Context Packet**.
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

The graph is updated by the LLM during conversation analysis or after web research. Before every model call, the agent pulls a "relevant context" summary from the graph based on the current active topics, ensuring it stays grounded in what it already knows.

## 3. Primitive Concept Engine (`primitive_concept_engine.py`)
This layer sits *below* the LLM. It detects patterns purely through structural observation.
Every tick, it captures a `StateSnapshot` (graph size, pressure values, active topics). It compares snapshots to detect "gaps" (e.g., topics that keep appearing without being resolved into the knowledge graph).
When a gap persists, it generates "Concept Pressure". If this pressure crosses a threshold, the engine aggregates the facts and asks the LLM to name a **Tentative Concept**.
Tentative concepts track `support` and `contradiction` over time. If they prove stable, they graduate to permanent nodes in the knowledge graph. This allows the system to learn structurally before it understands semantically.
