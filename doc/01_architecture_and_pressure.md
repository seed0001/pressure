# Architecture and Pressure

The Living Conversational Container is a pressure-regulated field organism. Its
visible behavior is conversation, but the runtime is organized around internal
state that keeps moving when the user is silent.

## Runtime Spine

`pressure_engine.py` is the main integration point. It owns the pressure buckets,
memory organs, metabolic state, ecology bridge, action dispatch, model calls,
and persistence.

The server and chat surfaces do not decide what the entity is. They feed signals
into the spine and expose its state.

## Tick Loop

The system advances in ticks. A tick can be triggered by the web dashboard,
mobile UI, chat interaction, or manual API call.

Each tick has three pressure phases:

1. Charge: current signals add pressure to buckets.
2. Flow: pressure moves along graph edges between buckets.
3. Discharge: a bucket that crosses its threshold may fire an action.

This means time matters. The organism can continue settling, becoming curious,
resting, or consolidating while no new message is arriving.

## Pressure Buckets

The current buckets are:

- `Decompress`: pressure to soften stress or restore ease.
- `Contribute`: pressure to be useful.
- `Learn`: pressure to investigate a knowledge gap.
- `Connect`: pressure to re-establish contact.
- `Curiosity`: pressure to ask, notice, or pursue novelty.
- `Focus`: pressure to center the main thread.
- `Clarify`: pressure to resolve uncertainty.
- `Reflect`: pressure to mirror meaning back.
- `Bond`: pressure to deepen the relationship.
- `Contemplate`: pressure to think privately.

The buckets are not isolated. Pressure can flow between them, so a knowledge gap
can become curiosity, curiosity can become connection, and contemplation can
feed later questions.

## New Signals

The merged runtime adds signals that did not exist in the original pressure
project:

- `metabolic_rest_drive`: rises when ATP is low or fatigue is high.
- `ecology_entropy_shift`: movement in the internal ecology's entropy.
- `ecology_diversity`: how diverse the ecology is.
- `ecology_lineage_flux`: change in territorial dominance.
- `ecology_stagnation`: low movement in the ecology.
- `ecology_novelty`: combined novelty pressure from ecological change.

These signals make metabolism and ecology consequential. They are not only
diagnostics.

## Actions

Pressure can dispatch:

- `reach_out`: visible speech/chat.
- `research`: live or dry-run information seeking.
- `internal_thought`: private reflection that may later raise pressure.

Research is metabolically gated. If ATP is too low or fatigue is too high,
research is blocked with `metabolic_rest` and the pressure remains instead of
forcing the organism through exhaustion.

## Speech Gravity

Speech is not free. When the entity speaks, the engine estimates remaining
listening time, overlap cost, and settling pressure. These costs make other
actions harder to fire while the previous expression is still being received.

This is not a fixed cooldown. It is a small pacing field that makes expression
have weight.

## Presence

Presence signals come from browser or local vision state. Face/attention
presence relieves absence and relationship pressure, especially `Connect`,
`Bond`, and `Decompress`.

Presence does not flatten the whole organism. Curiosity, learning, reflection,
and focus can continue moving while the user is present.

## Persistence

`save_state()` persists:

- pressure bucket values;
- chat and internal journals;
- symbolic pressure memory;
- mycelial field memory;
- metabolism;
- ecology bridge state;
- compatibility knowledge graph.

On load, the system restores those organs and resumes from the saved tick count.

## Architectural Principle

Avoid hard-coded personality shortcuts. A behavior should preferably emerge from
pressure, memory resonance, metabolic cost, ecology, or presence.
