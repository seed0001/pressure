"""
Conversation Analyzer — turns raw chat history into a structured context packet.

Runs after each user message. Feeds richer signals into the pressure engine
instead of relying on simple counters.

The LLM is a sensor here, not the god-engine. It reads and reports.
The pressure system decides what to do with what it finds.
"""

import json
import re

# ---------------------------------------------------------------------------
# Context packet schema (what the analyzer returns)
# ---------------------------------------------------------------------------
# {
#   "active_topics":      ["divorce", "Alabama", "identity"],      # recurring subjects
#   "emotional_charge":   ["grief", "trust", "loneliness"],        # dominant tone signals
#   "unresolved_openings": ["asked about moving plan, no answer"], # dangling threads
#   "curiosity_targets":  ["why Alabama specifically"],            # things agent wants to know
#   "relationship_state": {"trust": "rising", "tension": "falling"},
#   "focus_candidate":    "rebuilding identity after divorce",     # what this is really about
#   "conversation_depth": 0.0-1.0,   # how much weight has accumulated
#   "emotional_weight":   0.0-1.0,   # how charged the last message was
#   "new_inference_count": int,       # graph edges the analyzer found that weren't there before
# }

EMPTY_PACKET = {
    "active_topics":       [],
    "emotional_charge":    [],
    "unresolved_openings": [],
    "curiosity_targets":   [],
    "relationship_state":  {},
    "focus_candidate":     "",
    "conversation_depth":  0.0,
    "emotional_weight":    0.0,
    "new_inference_count": 0,
}

ANALYZE_SYSTEM = """You are a conversation analysis engine. You read a chat history and produce a structured snapshot of its current state.

Output ONLY valid JSON — no prose, no markdown fences. Use this exact shape:
{
  "active_topics": ["..."],
  "emotional_charge": ["..."],
  "unresolved_openings": ["..."],
  "curiosity_targets": ["..."],
  "relationship_state": {"trust": "rising|falling|stable", "connection": "rising|falling|stable", "tension": "rising|falling|stable"},
  "focus_candidate": "...",
  "conversation_depth": 0.0,
  "emotional_weight": 0.0,
  "new_inference_count": 0
}

Definitions:
- active_topics: subjects that came up at least twice, or are clearly central. Max 6. Short noun phrases.
- emotional_charge: the emotional tones present in the LAST 3 messages. Pick from: calm, grief, trust, excitement, frustration, loneliness, hope, anxiety, anger, warmth, sadness, confusion, relief. Max 4.
- unresolved_openings: questions the user asked that weren't answered, or topics they raised and then dropped. Concrete strings. Max 4.
- curiosity_targets: things a caring listener would naturally want to know more about given this conversation. Max 4.
- relationship_state: honest assessment of trajectory. Only include keys where direction is clear.
- focus_candidate: ONE plain-English phrase capturing what this conversation is really about right now.
- conversation_depth: 0.0 = surface small talk, 1.0 = the deepest personal disclosure. Be honest.
- emotional_weight: 0.0 = neutral last message, 1.0 = highly charged last message.
- new_inference_count: integer count of meaningful new facts or connections you noticed that weren't stated directly.

Rules:
- Do not invent. Only report what is actually in the conversation.
- If the conversation is short or shallow, most fields will be empty or low.
- If nothing meaningful is present, return the schema with empty arrays and 0.0 values.
"""


def analyze(history: list[dict], call_model_fn, tick: int = 0) -> dict:
    """
    Analyze the conversation history and return a context packet.
    Falls back to EMPTY_PACKET on any error.

    history: [{role, content}] — the last N messages
    call_model_fn: pressure_engine.call_model (passed in to avoid circular import)
    """
    if not history or len(history) < 2:
        return dict(EMPTY_PACKET)

    # build a compact transcript for the model (last 12 messages max)
    window = history[-12:]
    transcript_lines = []
    for msg in window:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if content:
            label = "User" if role == "user" else "Agent"
            # trim very long messages to keep the analysis prompt tight
            if len(content) > 300:
                content = content[:300] + "…"
            transcript_lines.append(f"{label}: {content}")

    transcript = "\n".join(transcript_lines)
    prompt = f"Analyze this conversation:\n\n{transcript}"

    try:
        raw = call_model_fn(ANALYZE_SYSTEM, [{"role": "user", "content": prompt}])
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        packet = json.loads(raw)
        # fill any missing keys with defaults
        result = dict(EMPTY_PACKET)
        result.update(packet)
        # clamp floats
        result["conversation_depth"] = float(max(0.0, min(1.0, result.get("conversation_depth", 0.0))))
        result["emotional_weight"]   = float(max(0.0, min(1.0, result.get("emotional_weight", 0.0))))
        result["new_inference_count"] = int(max(0, result.get("new_inference_count", 0)))
        return result
    except Exception:
        return dict(EMPTY_PACKET)


def packet_to_signal_deltas(packet: dict) -> dict:
    """
    Convert an analysis packet into signal value updates for the pressure engine.

    Returns a dict of signal_name -> new_value (0.0-1.0).
    The engine merges these into its current signals before the next tick.

    This is the translation layer between LLM perception and numeric pressure.
    """
    depth   = packet.get("conversation_depth", 0.0)
    weight  = packet.get("emotional_weight", 0.0)
    gaps    = len(packet.get("unresolved_openings", []))
    infer   = packet.get("new_inference_count", 0)
    topics  = len(packet.get("active_topics", []))
    charges = packet.get("emotional_charge", [])
    rel     = packet.get("relationship_state", {})

    # user_stress: emotional weight + grief/frustration/anxiety in charge
    stress_charges = {"grief", "frustration", "anxiety", "anger", "sadness", "confusion"}
    stress_boost = sum(0.15 for c in charges if c in stress_charges)
    user_stress = min(1.0, weight * 0.6 + stress_boost)

    # knowledge_gap: unresolved openings + curiosity targets signal gaps
    curiosity = len(packet.get("curiosity_targets", []))
    knowledge_gap = min(1.0, (gaps * 0.2) + (curiosity * 0.1) + (0.2 if infer > 2 else 0.0))

    # conversation_depth feeds directly as a signal
    conversation_depth = depth

    # unresolved_topics: count of hanging threads, normalized
    unresolved_topics = min(1.0, gaps * 0.25)

    # emotional_weight: direct pass-through
    emotional_weight = weight

    # new_inference_count: normalized
    new_inference_count = min(1.0, infer * 0.2)

    # relationship trajectory boosts
    trust_boost = 0.0
    if rel.get("trust") == "rising" or rel.get("connection") == "rising":
        trust_boost = 0.15
    if rel.get("tension") == "rising":
        user_stress = min(1.0, user_stress + 0.1)

    return {
        "user_stress":          round(user_stress, 3),
        "knowledge_gap":        round(knowledge_gap, 3),
        "conversation_depth":   round(conversation_depth, 3),
        "unresolved_topics":    round(unresolved_topics, 3),
        "emotional_weight":     round(emotional_weight, 3),
        "new_inference_count":  round(new_inference_count, 3),
        # preserve existing signals — caller merges, not replaces
    }
