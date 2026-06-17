# Analysis, Memory, Metabolism, and Ecology

The Living Conversational Container has several layers of perception and memory.
They do not all mean the same thing. A first mention is not durable memory; a
stable memory is something that has survived pressure, resonance, and time.

## Conversation Analyzer

`conversation_analyzer.py` converts recent dialogue and optional visual context
into a structured packet.

It can identify:

- active topics;
- emotional charge;
- unresolved openings;
- curiosity targets;
- relationship state;
- conversation depth;
- unstructured presence.

Those outputs become pressure signals. The analyzer does not directly decide
what the entity says; it changes the internal field that later actions emerge
from.

## Symbolic Pressure Memory

`pressure_memory.py` is the symbolic memory layer.

Extracted concepts enter a volatile pressure graph. Nodes and edges carry:

- pressure;
- stability;
- volatility;
- persistence;
- activation history;
- pathway diversity;
- weighted relations.

First-contact material is intentionally not projectable. It must be reactivated,
connected, and stabilized before it can appear in prompt context or the
compatibility knowledge graph.

This preserves the rule: memory is pressure before it is storage.

## Mycelial Field Memory

`mycelial_field.py` is the resonance memory organ. It is adapted from the
Mycelial Cortex idea, but stripped down into a dependency-free Python runtime.

It provides:

- sparse vector templates for concepts and relations;
- content-addressable recall by similarity/resonance;
- novelty growth when a pattern does not match existing nodes;
- consolidation when a familiar pattern returns;
- ATP-gated growth;
- ordered sparse token emission;
- chirality metadata (`chi`) for temporal direction;
- merge-on-consolidate for redundant fragments.

The field emits tokens with:

- `seq`: ordered token sequence;
- `tick`: engine tick;
- `node`: winning node;
- `prev_node`: previous winner;
- `chi`: simple direction marker;
- `payload`: sparse vector indices and values.

This is the foundation for future federation. Ordered token delivery matters
because sequence is part of experience.

## Merge-on-Consolidate

Fragmentation is a known risk. Without merging, similar patterns can spawn
multiple nodes and consume the memory budget.

The field now compares nodes during learning/settling. If two templates exceed
the merge threshold, the stronger node absorbs the weaker one:

- vectors blend;
- facts merge;
- activation and stability combine;
- winner history is rewritten to the surviving node;
- token history is updated;
- a merge event is recorded.

This keeps memory from shattering into redundant fragments.

## Metabolism

`metabolism.py` tracks:

- ATP;
- fatigue;
- rest drive;
- last demand;
- total spent;
- recall gain;
- whether growth is currently allowed.

Memory ingestion costs ATP. High fatigue or low ATP prevents new field growth.
Research can be blocked when the organism is below its usable energy floor.

Metabolism is therefore not decoration. It changes what the system can do.

## Ecology Bridge

`ecology_bridge.py` is the pressure-facing adapter for `computational-life`.

It accepts metrics such as:

- high-order entropy;
- unique program count;
- population size;
- territorial dominance;
- epoch.

It maps them into pressure signals:

- entropy shift feeds reflective pressure;
- diversity feeds reflection/focus;
- lineage flux feeds curiosity;
- stagnation feeds contemplation;
- novelty feeds curiosity.

At present this bridge accepts metrics through `POST /api/ecology_metrics`. A
dedicated Rust exporter for the `computational-life` repo is still a future
piece.

## Compatibility Knowledge Graph

`knowledge_graph.py` remains as a compatibility and presentation layer. It is no
longer the primary meaning of memory.

Stable symbolic pressure memory can project into the graph. The graph then gives
older UI and summary paths a familiar node/edge surface without reintroducing
instant storage as the core memory model.

## Vision

`vision_sensor.py` accepts browser-camera frames and can optionally use a local
camera if OpenCV is available.

Vision state includes:

- person presence;
- face presence;
- face count;
- attention;
- motion level;
- brightness;
- scene change;
- camera blockage.

Presence is used to satisfy absence pressure and ground prompts. If OpenCV is
not available, the server can still boot in browser/no-camera mode.
