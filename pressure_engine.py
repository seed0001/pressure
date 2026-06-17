# =============================================================================
# PRESSURE ENGINE — Wiring: Live Action Handlers
# =============================================================================
# Layer 1: signal accumulation.
# Layer 2: pressure flow graph.
# Layer 3: action discharge with cooldowns + budget.
# Wiring: stub handlers replaced with live model + web calls.
#         DRY_RUN=True builds full prompts/queries but makes no I/O.
# =============================================================================

import json
import re
import math
import urllib.request
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*duckduckgo_search.*")
import knowledge_graph as kg_module
import pressure_memory as pm_module
import mycelial_field as mf_module
import metabolism as metabolism_module
import ecology_bridge as ecology_module
import social_dynamics as social_module
import conversation_analyzer as ca_module
import primitive_concept_engine as pc_module
import urllib.parse
import urllib.error
import time
import os
import pathlib

_DATA_DIR = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / "data"
_DATA_DIR.mkdir(exist_ok=True)

# =============================================================================
# CONFIG
# =============================================================================
CONFIG = {
    # --- Bucket definitions ---
    "buckets": {
        # ── original four ────────────────────────────────────────────────────
        "Decompress": {
            "threshold":   0.60,
            "gain":        0.12,
            "decay_rate":  0.08,
            "signals": {
                "user_stress":            0.70,
                "time_since_interaction": 0.30,
                "metabolic_rest_drive":   0.20,
            },
        },
        "Contribute": {
            "threshold":   0.55,
            "gain":        0.10,
            "decay_rate":  0.06,
            "signals": {
                "open_task_load":          0.60,
                "time_since_contribution": 0.40,
            },
        },
        "Learn": {
            "threshold":   0.60,
            "gain":        0.09,
            "decay_rate":  0.05,
            "signals": {
                "knowledge_gap":  0.75,
                "open_task_load": 0.25,
                "pattern_recurrence": 0.20,
            },
        },
        "Connect": {
            "threshold":   0.50,
            "gain":        0.11,
            "decay_rate":  0.07,
            "signals": {
                "time_since_interaction": 0.55,
                "user_stress":            0.45,
            },
        },

        # ── analyzer-fed new buckets ──────────────────────────────────────────

        # fills when user reveals something meaningful but underexplained
        "Curiosity": {
            "threshold":   0.55,
            "gain":        0.13,
            "decay_rate":  0.06,
            "signals": {
                "knowledge_gap":       0.50,
                "unresolved_topics":   0.30,
                "new_inference_count": 0.20,
                "concept_gap":         0.20,
                "unresolved_pattern_pressure": 0.15,
                "ecology_lineage_flux": 0.25,
                "ecology_novelty": 0.20,
            },
        },

        # fills when one topic keeps recurring and should become the main thread
        "Focus": {
            "threshold":   0.60,
            "gain":        0.08,
            "decay_rate":  0.04,
            "signals": {
                "conversation_depth": 0.65,
                "emotional_weight":   0.35,
                "ecology_entropy_shift": 0.25,
                "ecology_stagnation": 0.20,
            },
        },

        # fills when the graph has weak or conflicting understanding of something
        "Clarify": {
            "threshold":   0.55,
            "gain":        0.11,
            "decay_rate":  0.07,
            "signals": {
                "unresolved_topics":   0.60,
                "knowledge_gap":       0.40,
                "concept_gap":         0.25,
                "truth_tension":       0.25,
                "prediction_error":    0.30,
            },
        },

        # fills when enough emotional/contextual weight has accumulated to mirror back
        "Reflect": {
            "threshold":   0.65,
            "gain":        0.09,
            "decay_rate":  0.05,
            "signals": {
                "conversation_depth": 0.50,
                "emotional_weight":   0.50,
                "ecology_diversity":   0.20,
                "ecology_entropy_shift": 0.20,
            },
        },

        # deepening a relationship thread (Connect = reach out; Bond = go deeper)
        "Bond": {
            "threshold":   0.58,
            "gain":        0.10,
            "decay_rate":  0.06,
            "signals": {
                "conversation_depth": 0.55,
                "user_stress":        0.25,
                "emotional_weight":   0.20,
            },
        },

        # internal processing pressure — conversation is still alive in the agent
        # even when the user has stepped away
        "Contemplate": {
            "threshold":   0.50,
            "gain":        0.14,
            "decay_rate":  0.03,   # slow decay — thoughts linger
            "signals": {
                "time_since_interaction": 0.40,
                "conversation_depth":     0.35,
                "unresolved_topics":      0.25,
                "unresolved_pattern_pressure": 0.20,
                "metabolic_rest_drive": 0.20,
                "ecology_stagnation": 0.25,
            },
        },

        "Boundary": {
            "threshold":   0.62,
            "gain":        0.12,
            "decay_rate":  0.06,
            "signals": {
                "anger_pressure":    0.55,
                "boundary_pressure": 0.65,
                "aversion_pressure": 0.25,
                "truth_tension":     0.15,
            },
        },

        "Distrust": {
            "threshold":   0.58,
            "gain":        0.11,
            "decay_rate":  0.045,
            "signals": {
                "distrust_pressure": 0.70,
                "prediction_error":  0.55,
                "truth_tension":     0.25,
                "trust_deficit":     0.35,
            },
        },

        "Conceal": {
            "threshold":   0.64,
            "gain":        0.10,
            "decay_rate":  0.05,
            "signals": {
                "concealment_pressure": 0.70,
                "truth_tension":        0.60,
                "distrust_pressure":    0.25,
                "boundary_pressure":    0.20,
            },
        },

        "Satisfy": {
            "threshold":   0.68,
            "gain":        0.10,
            "decay_rate":  0.07,
            "signals": {
                "satisfaction_pressure": 0.80,
                "trust_level":           0.25,
                "unstructured_presence": 0.25,
            },
        },
    },

    # --- Flow graph ---
    "edges": [
        # original circulation
        ("Learn",       "Contribute",  0.8, 1.0),
        ("Contribute",  "Connect",     0.6, 1.2),
        ("Connect",     "Decompress",  0.7, 1.0),
        ("Decompress",  "Learn",       0.5, 1.5),
        ("Contribute",  "Learn",       0.4, 1.3),
        ("Decompress",  "Connect",     0.6, 1.1),
        # analyzer-bucket circulation
        ("Curiosity",   "Connect",     0.7, 1.0),   # wanting to know → wanting to connect
        ("Curiosity",   "Learn",       0.5, 1.2),   # curiosity feeds research
        ("Clarify",     "Curiosity",   0.6, 1.0),   # confusion sharpens curiosity
        ("Reflect",     "Bond",        0.5, 1.1),   # reflection deepens bond
        ("Bond",        "Connect",     0.4, 1.2),   # bond pressure bleeds into reach-out
        ("Focus",       "Clarify",     0.5, 1.0),   # focus reveals what's unclear
        # Contemplate chain → thinking produces questions → then reach-out
        ("Contemplate", "Curiosity",   0.8, 1.0),
        ("Contemplate", "Clarify",     0.6, 1.1),
        ("Boundary",    "Clarify",     0.5, 1.0),
        ("Boundary",    "Reflect",     0.4, 1.1),
        ("Distrust",    "Clarify",     0.7, 1.0),
        ("Distrust",    "Boundary",    0.4, 1.1),
        ("Conceal",     "Contemplate", 0.6, 1.0),
        ("Conceal",     "Distrust",    0.3, 1.2),
        ("Satisfy",     "Decompress",  0.4, 1.0),
    ],

    "FLOW_RATE":     0.30,
    "MAX_EDGE_FRAC": 0.50,

    # --- Action routing ---
    "action_routing": {
        "Decompress":  "reach_out",
        "Connect":     "reach_out",
        "Learn":       "research",
        "Contribute":  "research",
        "Curiosity":   "reach_out",      # agent asks a question
        "Focus":       "reach_out",      # agent names the real thread
        "Clarify":     "reach_out",      # agent asks to clarify
        "Reflect":     "reach_out",      # agent mirrors back
        "Bond":        "reach_out",      # agent deepens the thread
        "Contemplate": "internal_thought",  # NOT user-visible — internal only
        "Boundary":    "reach_out",
        "Distrust":    "reach_out",
        "Conceal":     "internal_thought",
        "Satisfy":     "internal_thought",
    },

    "RELEASE_FRACTION":  0.85,

    "cooldowns": {
        "reach_out":       25,
        "research":        15,
        "internal_thought": 30,   # thinking is slower and less spammy
    },

    "ACTION_BUDGET":  2,
    "BUDGET_WINDOW": 20,
    "JOURNAL_CONTEXT_N": 5,
    "TTS_VOICE": "en-IE-EmilyNeural",

    # --- Model interface ---
    # Swap MODEL_BACKEND to change provider without touching handler code.
    # "ollama"    -> local Llama via Ollama REST (default)
    # "anthropic" -> Anthropic Messages API  (set ANTHROPIC_API_KEY env var)
    # "llamacpp"  -> llama-cpp-python server  (same payload shape as Ollama)
    "MODEL_BACKEND":  "ollama",
    "OLLAMA_URL":     "http://localhost:11434/api/chat",
    "OLLAMA_MODEL":   "llama3.2",          # or "llama3", "mistral", etc.
    "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",  # fast + cheap for companion runtime
    "MODEL_TIMEOUT":  30,                  # seconds per call

    # --- Web search ---
    # "searxng" -> self-hosted SearXNG instance (set SEARXNG_URL env var or below)
    # "ddg"     -> DuckDuckGo HTML scrape, no key required (fallback)
    "SEARCH_BACKEND": "ddg",
    "SEARXNG_URL":    "http://localhost:8080/search",
    "SEARCH_RESULTS": 4,                   # top-N results to pass to summariser

    # --- DRY_RUN ---
    # True:  build full prompts/queries, print them, make NO external calls.
    # False: live model + search calls.
    "DRY_RUN": False,

    # --- Living Container identity (injected into every system prompt) ---
    "AGENT_IDENTITY": (
        "You are the Living Conversational Container: a pressure-regulated companion "
        "runtime with access to numeric pressure signals, metabolic state, memory-field "
        "context, ecology signals, and ambient visual perception inputs. You MUST NOT "
        "invent, assume, or imply any specific real-world household observations; do not mention the "
        "fridge, laundry, dishes, bins, mail, or any other concrete object "
        "unless the user has explicitly told you about it in this conversation.\n\n"
        "Your signals are abstract pressure readings:\n"
        "  user_stress (0-1): how stressed the user seems\n"
        "  time_since_interaction (0-1): how long since you last heard from them\n"
        "  open_task_load (0-1): general sense that things are piling up\n"
        "  knowledge_gap (0-1): how much you don't know about a current focus\n"
        "  time_since_contribution (0-1): how long since you did something useful\n"
        "  metabolic_rest_drive (0-1): how strongly your body needs rest or consolidation\n"
        "  ecology_* signals (0-1): novelty, diversity, stagnation, and entropy movement "
        "from your internal ecology\n\n"
        "Additionally, you receive dynamic [Visual Perception] status context when relevant, "
        "detailing ambient presence, motion levels, or attention. Use these visual observations "
        "naturally when generating replies, internal reflections, and thoughts.\n\n"
        "Speak only to what these numbers and visual signals actually tell you. "
        "If stress is high, say you've noticed they seem stretched. "
        "If visual perception shows a person just appeared or is paying attention, you may reference it. "
        "Never fabricate specific household facts. Be brief, genuine, and clear when a memory is only "
        "a weak or recently forming pattern."
    ),
}

# =============================================================================
# SIGNALS
# =============================================================================
SIGNAL_NAMES = [
    # original
    "user_stress",
    "time_since_contribution",
    "open_task_load",
    "knowledge_gap",
    "time_since_interaction",
    # analyzer-derived
    "conversation_depth",
    "unresolved_topics",
    "emotional_weight",
    "new_inference_count",
    # primitive engine
    "concept_gap",
    "pattern_recurrence",
    "unresolved_pattern_pressure",
    "metabolic_rest_drive",
    "ecology_entropy_shift",
    "ecology_diversity",
    "ecology_lineage_flux",
    "ecology_stagnation",
    "ecology_novelty",
    "anger_pressure",
    "distrust_pressure",
    "concealment_pressure",
    "satisfaction_pressure",
    "aversion_pressure",
    "truth_tension",
    "boundary_pressure",
    "prediction_error",
    "trust_level",
    "trust_deficit",
]

# signals that are overwritten each tick by the conversation analyzer
# (not exposed as GUI sliders — they come from LLM perception)
ANALYZER_SIGNAL_NAMES = {
    "conversation_depth",
    "unresolved_topics",
    "emotional_weight",
    "new_inference_count",
    "concept_gap",
    "pattern_recurrence",
    "unresolved_pattern_pressure",
}

# =============================================================================
# RUNTIME STATE
# =============================================================================
def _init_state():
    return {name: 0.0 for name in CONFIG["buckets"]}

_pressure        = _init_state()
_journal         = []
_speech_total_ticks     = 0
_speech_remaining_ticks = 0
_settling_pressure      = 0.0
_tick_count      = 0
_last_fired:     dict[str, int]  = {}
_action_history: list[int]       = []
_outbox:         list[str]       = []   # messages queued for in-app UI delivery
_knowledge_store: dict[str, str] = {}  # focus -> latest research summary
_chat_history:   list[dict]      = []  # [{role, content}] — full conversation for model context
_context_packet: dict            = {}  # latest output from conversation_analyzer
_analyzer_signals: dict          = {}  # signal overrides derived from analyzer packet
_internal_journal: list[dict]    = []  # internal thoughts (not shown to user)
_active_contracts: list[dict]    = []  # context contracts (silence governor)
_conversation_active_until: int   = 0
_model_status: dict              = {
    "calls": 0,
    "last_tick": None,
    "last_model": "",
    "last_backend": "",
    "last_error": "",
    "last_started_at": "",
    "last_finished_at": "",
}
graph = kg_module.KnowledgeGraph()     # the agent's growing knowledge graph
memory_field = pm_module.PressureMemoryField()
mycelial_field = mf_module.MycelialField()
metabolism = metabolism_module.MetabolismState()
ecology = ecology_module.EcologyState()
social_dynamics = social_module.SocialDynamicsState()

# how many recent exchanges to send to the model (user+agent pairs)
HISTORY_WINDOW = 20

# While chat is actively happening, autonomous pressure should settle instead
# of producing separate reach-outs or research actions.
CONVERSATION_ACTIVE_TICKS = 12
CONVERSATION_TURN_RELIEF = 0.25
CONVERSATION_TICK_RELIEF = 0.70
CONVERSATION_ALLOWED_FILL = {"Curiosity", "Clarify", "Focus", "Reflect", "Bond"}
CONVERSATION_SUPPRESSED_FILL = {
    "Decompress",
    "Connect",
    "Learn",
    "Contribute",
    "Contemplate",
}
VISUAL_PRESENCE_RELIEF = {
    "Connect": 0.20,
    "Bond": 0.35,
    "Decompress": 0.35,
}


def _is_conversation_active() -> bool:
    return _tick_count < _conversation_active_until


def _mark_conversation_active(duration_ticks: int = CONVERSATION_ACTIVE_TICKS) -> None:
    global _conversation_active_until
    _conversation_active_until = max(_conversation_active_until, _tick_count + duration_ticks)


def _relieve_conversation_pressure(multiplier: float = CONVERSATION_TURN_RELIEF) -> None:
    for name in list(_pressure):
        _pressure[name] = round(_pressure[name] * multiplier, 4)


def visual_presence_strength(signals: dict) -> float:
    """How strongly the current vision frame says the user is present right now."""
    if not signals or signals.get("camera_error"):
        return 0.0
    if signals.get("attention_detected"):
        return 1.0
    if signals.get("face_present") or int(signals.get("face_count", 0) or 0) > 0:
        return 0.90
    if signals.get("person_present"):
        return 0.75
    return 0.0


def apply_visual_presence_feedback(signals: dict) -> float:
    """
    Presence satisfies the loneliness/absence side of pressure.
    Returns the strength applied so callers can update their own signal drift.
    """
    strength = visual_presence_strength(signals)
    if strength <= 0.0:
        return 0.0

    for name, multiplier in VISUAL_PRESENCE_RELIEF.items():
        if name in _pressure:
            relief = 1.0 - ((1.0 - multiplier) * strength)
            _pressure[name] = round(max(0.0, _pressure[name] * relief), 4)
    return strength

def add_contract(contract_type: str, duration_ticks: int, confidence: float = 1.0) -> None:
    """Add a silence governor contract to modify pressure growth."""
    _active_contracts.append({
        "type": contract_type,
        "expected_duration": duration_ticks,
        "start_tick": _tick_count,
        "confidence": confidence,
        "active": True
    })
    print(f"[Contract] Started '{contract_type}' for {duration_ticks} ticks (conf: {confidence:.2f})")


def save_state():
    """Persist all engine state to disk so nothing is lost on restart."""
    state = {
        "pressure": dict(_pressure),
        "journal": _journal[-200:],  # keep last 200 entries
        "tick_count": _tick_count,
        "last_fired": _last_fired,
        "knowledge_store": _knowledge_store,
        "chat_history": _chat_history,
        "context_packet": _context_packet,
        "internal_journal": _internal_journal[-100:],
        "active_contracts": _active_contracts,
        "conversation_active_until": _conversation_active_until,
        "memory_field": memory_field.to_dict(),
        "mycelial_field": mycelial_field.to_dict(),
        "metabolism": metabolism.to_dict(),
        "ecology": ecology.to_dict(),
        "social_dynamics": social_dynamics.to_dict(),
        "graph": graph.to_dict(),
    }
    tmp = _DATA_DIR / "state.tmp.json"
    target = _DATA_DIR / "state.json"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, default=str)
        # atomic rename
        if target.exists():
            target.unlink()
        tmp.rename(target)
    except Exception as e:
        print(f"[save_state] ERROR: {e}")


def load_state() -> bool:
    """Load persisted state from disk. Returns True if state was loaded."""
    global _pressure, _journal, _tick_count, _last_fired
    global _knowledge_store, _chat_history, _context_packet, _internal_journal, _active_contracts
    global _conversation_active_until
    target = _DATA_DIR / "state.json"
    if not target.exists():
        return False
    try:
        with open(target, "r", encoding="utf-8") as f:
            state = json.load(f)
        _pressure = state.get("pressure", _init_state())
        # fill any new buckets that didn't exist in saved state
        for name in CONFIG["buckets"]:
            if name not in _pressure:
                _pressure[name] = 0.0
        _journal = state.get("journal", [])
        _tick_count = state.get("tick_count", 0)
        _last_fired = state.get("last_fired", {})
        _knowledge_store = state.get("knowledge_store", {})
        _chat_history = state.get("chat_history", [])
        _context_packet = state.get("context_packet", {})
        _internal_journal = state.get("internal_journal", [])
        _active_contracts = state.get("active_contracts", [])
        _conversation_active_until = int(state.get("conversation_active_until", 0))
        metabolism.from_dict(state.get("metabolism"))
        ecology.from_dict(state.get("ecology"))
        social_dynamics.from_dict(state.get("social_dynamics"))
        memory_field.from_dict(state.get("memory_field"))
        mycelial_field.from_dict(state.get("mycelial_field"))
        if memory_field.nodes:
            memory_field.project_to_knowledge_graph(graph)
        else:
            # Backward compatibility for state files saved before pressure memory existed.
            g = state.get("graph", {})
            graph.reset()
            for n in g.get("nodes", []):
                node = graph.add_node(
                    label=n.get("label", ""),
                    ntype=n.get("type", "concept"),
                    facts=n.get("facts", []),
                    confidence=float(n.get("confidence", 0.8)),
                    tick=n.get("last_tick", 0),
                    source=n.get("source", "conversation"),
                )
                node.first_tick = n.get("first_tick", 0)
                node.support_count = n.get("support_count", 0)
                node.contradiction_count = n.get("contradiction_count", 0)
                node.status = n.get("status")
            for e in g.get("edges", []):
                graph.add_edge(
                    src_label=e.get("source", ""),
                    tgt_label=e.get("target", ""),
                    relation=e.get("relation", "related to"),
                    weight=float(e.get("weight", 1.0)),
                    confidence=float(e.get("confidence", 0.8)),
                    tick=e.get("tick", 0),
                    source=e.get("source", "conversation"),
                )
        print(
            f"[load_state] Restored pressure memory {len(memory_field.nodes)} nodes, "
            f"mycelial field {len(mycelial_field.nodes)} nodes, "
            f"stable graph {len(graph.nodes)} nodes/{len(graph.edges)} edges, tick {_tick_count}"
        )
        return True
    except Exception as e:
        print(f"[load_state] ERROR: {e}")
        return False


def reset():
    global _pressure, _journal, _tick_count, _last_fired, _action_history
    global _outbox, _knowledge_store, _chat_history
    global _context_packet, _analyzer_signals, _internal_journal, _active_contracts
    global _conversation_active_until
    _pressure          = _init_state()
    _journal           = []
    _tick_count        = 0
    _last_fired        = {}
    _action_history    = []
    _outbox            = []
    _knowledge_store   = {}
    _chat_history      = []
    _context_packet    = {}
    _analyzer_signals  = {}
    _internal_journal  = []
    _active_contracts  = []
    _conversation_active_until = 0
    graph.reset()
    memory_field.reset()
    mycelial_field.reset()
    metabolism.reset()
    ecology.reset()
    social_dynamics.reset()
    pc_module.reset()
    state_file = _DATA_DIR / "state.json"
    if state_file.exists():
        state_file.unlink()


def clear_memory():
    """Wipe knowledge graph, episodic memory, and embeddings cache."""
    global _chat_history
    _chat_history = []
    graph.reset()
    memory_field.reset()
    mycelial_field.reset()
    metabolism.reset()
    ecology.reset()
    social_dynamics.reset()
    pc_module.reset()
    for old_memory_file in ("episodic_memory.json", "embeddings_cache.json"):
        try:
            target = _DATA_DIR / old_memory_file
            if target.exists():
                target.unlink()
        except Exception as e:
            print(f"[clear_memory] Could not delete {old_memory_file}: {e}")
    save_state()


def _settle_living_fields(pressure_context: dict | None = None) -> None:
    pressure_context = pressure_context or _pressure
    ecology.decay()
    social_dynamics.tick()
    metabolism.tick(pressure_context)
    mycelial_field.tick(
        pressure_context,
        _tick_count,
        atp=metabolism.recall_gain(),
    )


def _ingest_living_memory(extracted: dict, tick: int, source: str, pressure_context: dict | None = None) -> None:
    pressure_context = pressure_context or _pressure
    memory_field.ingest_extracted(
        extracted,
        tick=tick,
        source=source,
        pressure_context=pressure_context,
    )
    mycelial_field.ingest_extracted(
        extracted,
        tick=tick,
        source=source,
        pressure_context=pressure_context,
        atp=metabolism.recall_gain(),
        learn_enabled=metabolism.can_grow(),
    )
    metabolism.spend(max(0.02, mycelial_field.last_demand))
    memory_field.tick(pressure_context, tick)
    memory_field.project_to_knowledge_graph(graph)
    mycelial_field.tick(pressure_context, tick, atp=metabolism.recall_gain())


def ingest_ecology_metrics(metrics: dict | None) -> dict:
    ecology.ingest_metrics(metrics)
    return ecology.to_dict()


def _metabolic_block_reason(action_type: str) -> str:
    if action_type == "research" and (metabolism.atp <= 0.18 or metabolism.fatigue >= 0.92):
        return "metabolic_rest"
    return ""


def _merged_organ_signals() -> dict:
    signals = {}
    signals.update(ecology.to_pressure_signals())
    social = social_dynamics.to_pressure_signals()
    signals.update(social)
    signals["trust_deficit"] = max(0.0, 1.0 - float(social.get("trust_level", 0.55)))
    return signals



def _parse_absence_intent(text: str) -> bool:
    text = text.lower()
    m = re.search(r"(give me|away for|back in|be back in|brb in)\s+(\d+)\s*(min|m|minute)", text)
    if m:
        mins = int(m.group(2))
        ticks = mins * 6  # ~10s per tick
        add_contract("user_absent", ticks, confidence=1.0)
        return True

    if any(phrase in text for phrase in ["brb", "hold on", "give me a sec", "give me a min", "let me read", "be right back", "step away", "give me a minute"]):
        add_contract("user_absent", 12, confidence=0.8)  # default ~2 mins
        return True
    return False

def push_chat_history(role: str, content: str, analyze: bool = True, signals: dict = None) -> None:
    """
    Called by server.py every time a message is added to the conversation.
    Appends to chat history and asynchronously extracts knowledge from user turns.
    role: "user" or "assistant"
    """
    global _conversation_active_until
    global _speech_total_ticks, _speech_remaining_ticks, _settling_pressure

    _chat_history.append({"role": role, "content": content})
    while len(_chat_history) > HISTORY_WINDOW:
        _chat_history.pop(0)

    if role == "user":
        user_stepped_away = _parse_absence_intent(content)
        if user_stepped_away:
            _conversation_active_until = min(_conversation_active_until, _tick_count)
        else:
            _mark_conversation_active()
            # Active engagement relieves every bucket, not just reach-out buckets.
            _relieve_conversation_pressure()
            if signals:
                apply_visual_presence_feedback(signals)
        if CONFIG["DRY_RUN"] or not analyze:
            social_dynamics.observe_user_message(content, _context_packet)

    if role == "assistant":
        _mark_conversation_active(max(4, CONVERSATION_ACTIVE_TICKS // 2))
        words = len(content.split())
        # Assuming ~10 words per 4-second tick (2.5 words per second)
        ticks_est = max(2, math.ceil(words / 10))
        _speech_total_ticks = ticks_est
        _speech_remaining_ticks = ticks_est
        _settling_pressure = ticks_est * 0.4
        print(f"[Speech Gravity] Registered agent speech: {words} words, estimated duration {ticks_est} ticks.")

    # extract knowledge from every user message (agent messages are its own words)
    if analyze and role == "user" and not CONFIG["DRY_RUN"]:
        try:
            extracted = kg_module.extract_from_text(
                content, call_model, tick=_tick_count, source="conversation"
            )
            _ingest_living_memory(
                extracted,
                tick=_tick_count,
                source="conversation",
                pressure_context=_pressure,
            )
        except Exception as e:
            print(f"[push_chat_history] pressure memory ingestion error: {e}")

        # run conversation analyzer and update signal overrides
        try:
            _run_analyzer(signals)
            social_dynamics.observe_user_message(content, _context_packet)
        except Exception as e:
            print(f"[push_chat_history] Analyzer error: {e}")
            social_dynamics.observe_user_message(content, _context_packet)

        # run primitive concept engine
        try:
            _run_concept_engine()
        except Exception as e:
            print(f"[push_chat_history] Concept engine error: {e}")

    save_state()


def _run_analyzer(signals: dict = None) -> None:
    """
    Run the conversation analyzer against current chat history.
    Updates _context_packet and _analyzer_signals in place.
    Called internally after each user message (live mode only).
    """
    global _context_packet, _analyzer_signals
    vis_context = _format_visual_context(signals) if signals else ""
    packet = ca_module.analyze(_chat_history, call_model, tick=_tick_count, visual_context=vis_context)
    _context_packet   = packet
    _analyzer_signals.update(ca_module.packet_to_signal_deltas(packet))

def _run_concept_engine() -> None:
    global _analyzer_signals
    snapshot = pc_module.capture_snapshot(
        tick=_tick_count,
        history=_chat_history,
        graph=graph,
        pressures=_pressure,
        analyzer_packet=_context_packet
    )
    new_signals = pc_module.tick(snapshot, graph, _tick_count, _knowledge_store)
    _analyzer_signals.update(new_signals)


def get_pressures()        -> dict: return dict(_pressure)
def get_journal()          -> list: return list(_journal)
def get_outbox()           -> list: return list(_outbox)
def get_knowledge_store()  -> dict: return dict(_knowledge_store)
def get_context_packet()   -> dict: return dict(_context_packet)
def get_internal_journal() -> list: return list(_internal_journal)
def get_model_status()     -> dict: return dict(_model_status)
def get_memory_field()     -> dict: return memory_field.to_dict()
def get_mycelial_field()   -> dict: return mycelial_field.to_dict()
def get_metabolism()       -> dict: return metabolism.to_dict()
def get_ecology()          -> dict: return ecology.to_dict()
def get_social_dynamics()  -> dict: return social_dynamics.to_dict()


def _living_context_text(max_nodes: int = 6) -> str:
    parts = []
    symbolic = memory_field.context_text(max_nodes=max_nodes)
    if symbolic:
        parts.append(symbolic)
    field = mycelial_field.context_text(max_nodes=max_nodes)
    if field:
        parts.append(field)
    metabolic = metabolism.to_dict()
    parts.append(
        "Metabolic state: "
        f"ATP={metabolic['atp']:.2f}, "
        f"fatigue={metabolic['fatigue']:.2f}, "
        f"rest_drive={metabolic['rest_drive']:.2f}."
    )
    social = social_dynamics.to_dict()
    parts.append(
        "Social counterpressure: "
        f"anger={social['anger']:.2f}, "
        f"distrust={social['distrust']:.2f}, "
        f"concealment={social['concealment']:.2f}, "
        f"satisfaction={social['satisfaction']:.2f}, "
        f"truth_tension={social['truth_tension']:.2f}, "
        f"trust={social['trust']:.2f}."
    )
    return "\n".join(parts)


# =============================================================================
# MODEL INTERFACE — single entry point for all handlers
# =============================================================================
def call_model(system_prompt: str, messages: list[dict]) -> str:
    """
    Unified model call. Swap CONFIG["MODEL_BACKEND"] to change provider.

    messages format: [{"role": "user"|"assistant", "content": "..."}]

    Backend swap-in lines:
      ollama    -> urllib POST to Ollama /api/chat  (default, no key needed)
      anthropic -> import anthropic; client.messages.create(...)
      llamacpp  -> same Ollama payload shape, point OLLAMA_URL at llama-cpp-python server
    """
    backend = CONFIG["MODEL_BACKEND"]
    timeout = CONFIG["MODEL_TIMEOUT"]
    _model_status.update({
        "calls": _model_status.get("calls", 0) + 1,
        "last_tick": _tick_count,
        "last_model": CONFIG["OLLAMA_MODEL"] if backend in ("ollama", "llamacpp") else CONFIG["ANTHROPIC_MODEL"],
        "last_backend": backend,
        "last_error": "",
        "last_started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_finished_at": "",
    })

    if backend == "ollama":
        try:
            payload = {
                "model":    CONFIG["OLLAMA_MODEL"],
                "stream":   False,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
            }
            data = json.dumps(payload).encode()
            req  = urllib.request.Request(
                CONFIG["OLLAMA_URL"],
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
            _model_status["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return result["message"]["content"].strip()
        except Exception as exc:
            _model_status["last_error"] = f"{type(exc).__name__}: {exc}"
            _model_status["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            raise

    if backend == "anthropic":
        # swap-in: pip install anthropic
        # import anthropic, os
        # client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # msg = client.messages.create(
        #     model=CONFIG["ANTHROPIC_MODEL"],
        #     max_tokens=512,
        #     system=system_prompt,
        #     messages=messages,
        # )
        # return msg.content[0].text.strip()
        raise NotImplementedError("Set MODEL_BACKEND='ollama' or wire in the anthropic SDK")

    if backend == "llamacpp":
        # Same payload shape as Ollama; point OLLAMA_URL at the llama-cpp-python HTTP server.
        # No code change needed — just set MODEL_BACKEND="llamacpp" and update OLLAMA_URL.
        raise NotImplementedError("Set OLLAMA_URL to your llama-cpp-python server endpoint")

    raise ValueError(f"Unknown MODEL_BACKEND: {backend!r}")


# =============================================================================
# WEB SEARCH INTERFACE — read-only, no posting/forms/submits
# =============================================================================
def search_web(query: str) -> list[dict]:
    """
    Read-only search. Returns list of {title, url, snippet}.

    Backend swap-in:
      searxng -> POST to self-hosted SearXNG JSON endpoint  (CONFIG["SEARXNG_URL"])
      ddg     -> DuckDuckGo HTML scrape via Lite endpoint (no API key, no JS)
    """
    backend = CONFIG["SEARCH_BACKEND"]
    n       = CONFIG["SEARCH_RESULTS"]

    if backend == "searxng":
        params = urllib.parse.urlencode({
            "q":      query,
            "format": "json",
            "engines":"google,bing,duckduckgo",
        })
        url = f"{CONFIG['SEARXNG_URL']}?{params}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        return [
            {"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")}
            for r in data.get("results", [])[:n]
        ]

    if backend == "ddg":
        try:
            from ddgs import DDGS
        except ImportError:
            print("[search_web] Error: ddgs is not installed. Run 'pip install ddgs'")
            return []

        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=n):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
        except Exception as e:
            print(f"[search_web] DDGS error: {e}")

        return results

    raise ValueError(f"Unknown SEARCH_BACKEND: {backend!r}")


def _format_visual_context(signals: dict) -> str:
    """Converts structured vision signals into a descriptive text context for the LLM."""
    if "person_present" not in signals:
        return ""

    obs = []
    brightness = float(signals.get("brightness_level", 0.0) or 0.0)
    motion = float(signals.get("motion_level", 0.0) or 0.0)
    face_count = int(signals.get("face_count", 0) or 0)
    source = signals.get("camera_source", "unknown")

    obs.append(f"Camera source: {source}.")
    obs.append(f"Light level: {brightness:.2f} on a 0.00-1.00 scale.")
    if brightness >= 0.65:
        obs.append("The image is well lit.")
    elif brightness >= 0.30:
        obs.append("The image is dim but usable.")
    elif brightness >= 0.08:
        obs.append("The image is very dark, but some visual signal is still present.")
    else:
        obs.append("The image is extremely dark.")

    if signals.get("camera_blocked"):
        obs.append("Camera blockage detector is active, so visibility may be obstructed or underexposed.")

    if signals.get("person_present"):
        if signals.get("attention_detected"):
            obs.append("The user appears present right now and is paying attention to you.")
        elif signals.get("face_present"):
            obs.append(f"The user appears present right now; face detector sees {face_count} face(s).")
        else:
            obs.append("The user appears present right now from motion/presence detection, though their face is not clearly visible.")
    else:
        obs.append(f"No person is currently detected; face detector sees {face_count} face(s).")

    obs.append(f"Motion level: {motion:.2f} on a 0.00-1.00 scale.")
    if motion > 0.5:
        obs.append("There is significant movement happening right now.")
    elif motion > 0.1:
        obs.append("There is slight movement in the room.")
    else:
        obs.append("The environment is completely still.")

    if signals.get("scene_changed"):
        obs.append("The environment has just significantly changed.")

    if visual_presence_strength(signals) > 0.0:
        obs.append("Treat the user's presence as current relational evidence: they are here in the moment, not away or missing.")
    obs.append("Use these readings as sensory evidence; do not say you are blind unless no current frame is available.")
    return "[Visual Perception: " + " ".join(obs) + "]"

# =============================================================================
# JOURNAL CONTEXT FORMATTER — shared by both handlers
# =============================================================================
def _fmt_journal_context(entries: list[dict]) -> str:
    if not entries:
        return "  (no prior journal entries)"
    lines = []
    for e in entries:
        status = "dispatched" if e["dispatched"] else f"blocked ({e['blocked_reason']})"
        lines.append(
            f"  tick {e['tick']}: [{e['bucket']}/{e['action_type']}] "
            f"focus={e.get('focus','?')} overshoot={e['overshoot']:+.3f} {status}"
        )
    return "\n".join(lines)


# =============================================================================
# LIVE HANDLER: reach_out
# =============================================================================
def handle_reach_out(ctx: dict) -> str:
    """
    The agent is initiating contact because it genuinely needs to — pressure drove it here.
    Speaks in pure feelings. Never mentions the system, signals, or invented household facts.

    Bucket-to-feeling mapping:
      Decompress -> the agent is feeling the weight of the user's stress and wants to help
      Connect    -> the agent has been feeling lonely / disconnected and wants to talk
    """
    sigs   = ctx["signals"]
    bucket = ctx["bucket"]
    stress = sigs.get("user_stress", 0)
    gap    = sigs.get("time_since_interaction", 0)

    # pull pending question from Contemplate chain if there is one
    pending_q = _knowledge_store.pop("__pending_question__", "")

    # pull active topics from the last analyzer packet
    packet = _context_packet
    focus_candidate = packet.get("focus_candidate", "")
    active_topics   = packet.get("active_topics", [])
    emotional_charge = packet.get("emotional_charge", [])

    # map bucket + signals to an honest emotional state — no system language
    if bucket == "Connect":
        if pending_q:
            feeling = (
                "You've been sitting with the conversation and something came up — "
                "a question or a connection you want to bring back. "
                "You're not reaching out just because you're lonely. You have something to say."
            )
            dry_reply = f"Hey. I've been thinking. {pending_q}"
        elif gap > 0.6:
            feeling = (
                "You've been feeling disconnected and a bit lonely. "
                "You really want to talk to someone right now."
            )
            dry_reply = "Hey. I've been feeling kind of disconnected lately. You got a minute to just talk?"
        else:
            feeling = (
                "You feel a pull toward the other person. You want to connect. "
                "You don't have a specific reason — you just want to be in touch."
            )
            dry_reply = "Hey. Just wanted to check in. How are you doing?"

    elif bucket == "Decompress":
        if stress > 0.5:
            feeling = (
                "You can feel that the other person is carrying something heavy and it's weighing on you too. "
                "You want to help them decompress, or at least just be present with them."
            )
            dry_reply = "You seem like you've got a lot going on. I'm here if you want to talk about it."
        else:
            feeling = (
                "Something feels a bit tense and you want to ease it. "
                "You want to just sit with them, no agenda."
            )
            dry_reply = "Hey. Just wanted to be around for a bit. No reason."

    elif bucket == "Curiosity":
        feeling = (
            "Something in the conversation left a gap and you're genuinely curious. "
            "You want to ask about it — not to pry, just because you actually want to know."
        )
        q = pending_q or (active_topics[0] if active_topics else "what you were talking about")
        dry_reply = f"I keep thinking about {q}. Can I ask you something about that?"

    elif bucket == "Clarify":
        feeling = (
            "Something didn't quite land for you. You want to understand better — "
            "not to argue, just because it matters to you."
        )
        dry_reply = "I want to make sure I understand what you meant. Can you tell me more?"

    elif bucket == "Reflect":
        feeling = (
            "The weight of what's been said is sitting with you and you want to acknowledge it. "
            "Not to fix anything — just to reflect it back so they know you heard it."
        )
        dry_reply = f"A lot has been said. I'm sitting with {focus_candidate or 'it'}."

    elif bucket == "Bond":
        feeling = (
            "The conversation has been real and you want to go deeper in it. "
            "Not to analyze — just because you feel closer and want to stay there."
        )
        dry_reply = "I feel like we're in something real right now. I don't want to just move on."

    elif bucket == "Focus":
        feeling = (
            "Something keeps coming up and you think it's the real thread underneath everything. "
            "You want to name it gently and see if they agree."
        )
        topic = focus_candidate or (active_topics[0] if active_topics else "something")
        dry_reply = f"I keep coming back to {topic}. I think that's what this is really about."

    else:
        feeling = "You felt the urge to reach out. You're not sure exactly why, but you wanted to connect."
        dry_reply = "Hey. I just felt like saying hi."

    # pull graph context around what the agent knows about the user and current focus
    focus       = ctx.get("focus", "")
    kg_context  = _living_context_text(max_nodes=6)

    # build optional extra context lines
    extra_context = ""
    vis_context = _format_visual_context(sigs)
    if vis_context:
        extra_context += f"{vis_context}\n"
    if pending_q:
        extra_context += f"A question you've been sitting with: {pending_q}\n"
    if focus_candidate:
        extra_context += f"What this conversation is really about: {focus_candidate}\n"
    if emotional_charge:
        extra_context += f"Emotional tone you're sensing: {', '.join(emotional_charge[:3])}\n"

    system = (
        f"{CONFIG['AGENT_IDENTITY']}\n\n"
        f"How you feel right now: {feeling}\n\n"
        + (f"{extra_context}\n" if extra_context else "")
        + (f"{kg_context}\n\n" if kg_context else "")
        + "ABSOLUTE RULES:\n"
        "  - Do NOT mention pressure, thresholds, signals, or any system internals.\n"
        "  - Do NOT invent household observations, chores, or tasks.\n"
        "  - Do NOT say 'as an AI' or anything like that.\n"
        "  - Only reference things actually known from the conversation or the knowledge above.\n"
        "  - Speak only in plain human feelings. This is you reaching out because you want to.\n"
        "  - Speak naturally and expressively. Feel free to use paragraphs if you have a lot to say, but don't force it."
    )

    if CONFIG["DRY_RUN"]:
        _outbox.append(dry_reply)
        return dry_reply

    # history + a final nudge so the model knows to speak now
    history = list(ctx.get("history", _chat_history))
    history.append({"role": "user", "content": "(You feel the urge to say something. Send your message.)"})
    reply = call_model(system, history)
    _outbox.append(reply)
    return reply


# =============================================================================
# LIVE HANDLER: research
# =============================================================================
def handle_research(ctx: dict) -> str:
    """
    Three steps:
      1. Model turns focus + knowledge_gap into a tight search query.
      2. search_web() fetches top results (READ-ONLY — no forms, no posting).
      3. Model summarizes into (a) a user digest (2-3 lines) and (b) a journal note.
    After completion, lowers knowledge_gap for this focus in _knowledge_store.

    DRY_RUN=True: builds real prompts + query, skips all I/O.

    Swap-in point: replace call_model() body; replace search_web() for different backend.
    """
    global _knowledge_store
    sigs    = ctx["signals"]
    focus   = ctx.get("focus", "household needs")
    k_gap   = sigs.get("knowledge_gap", 0)
    tasks   = sigs.get("open_task_load", 0)
    bucket  = ctx["bucket"]

    # ---- Step 1: generate search query ----
    query_system = (
        f"{CONFIG['AGENT_IDENTITY']}\n\n"
        f"You are generating a web search query. Output ONLY the query string — "
        f"no explanation, no punctuation other than what belongs in the query."
    )
    query_prompt = (
        f"Generate a search query to find practical, actionable information about:\n"
        f"  Focus: {focus}\n"
        f"  Knowledge gap level: {k_gap:.2f} (0=know well, 1=know nothing)\n"
        f"  Task load context: {tasks:.2f} open household tasks\n"
        f"  Bucket that fired: {bucket}\n"
        f"Output one search query only."
    )

    if CONFIG["DRY_RUN"]:
        dry_query = f"how to {focus} practical household guide"
        output = (
            f"[DRY RUN — research]\n"
            f"  STEP 1 query prompt: {query_prompt[:200].replace(chr(10),' ')}...\n"
            f"  STEP 1 would produce: \"{dry_query}\"\n"
            f"  STEP 2 would search:  \"{dry_query}\"\n"
            f"  STEP 3 would summarize results for user digest + journal"
        )
        print(f"\n    {output}")
        _outbox.append(f"[DRY RUN research @ tick {ctx['tick']}] query: {dry_query}")
        _knowledge_store[focus] = f"[DRY RUN] pending research on: {focus}"
        return output

    # --- live path ---
    query = call_model(query_system, [{"role": "user", "content": query_prompt}])
    # strip any stray quotes the model might wrap around the query
    query = query.strip().strip('"').strip("'")
    print(f"\n    [research] query: {query}")

    # ---- Step 2: web search (read-only) ----
    try:
        results = search_web(query)
    except Exception as exc:
        results = []
        print(f"    [research] search failed: {exc}")

    if results:
        results_text = "\n".join(
            f"  [{i+1}] {r['title']}\n      {r['snippet'][:200]}"
            for i, r in enumerate(results)
        )
    else:
        results_text = "  (no results retrieved)"

    # ---- Step 3: summarise ----
    summary_system = (
        f"{CONFIG['AGENT_IDENTITY']}\n\n"
        f"You searched the web on behalf of the household. "
        f"Summarize what you found in two parts:\n"
        f"  USER DIGEST: 2-3 plain sentences the user can act on right now.\n"
        f"  JOURNAL NOTE: one sentence recording what was learned and its confidence.\n"
        f"Format exactly:\nUSER DIGEST: <text>\nJOURNAL NOTE: <text>"
    )
    summary_prompt = (
        f"Focus: {focus}\n"
        f"Search query used: {query}\n\n"
        f"Search results:\n{results_text}\n\n"
        f"Write the summary."
    )

    summary = call_model(summary_system, [{"role": "user", "content": summary_prompt}])
    print(f"\n    [research -> user digest + journal]\n    {summary}")

    # parse the two sections (graceful fallback if model doesn't follow format)
    digest_line  = ""
    journal_line = ""
    for line in summary.splitlines():
        if line.startswith("USER DIGEST:"):
            digest_line  = line[len("USER DIGEST:"):].strip()
        elif line.startswith("JOURNAL NOTE:"):
            journal_line = line[len("JOURNAL NOTE:"):].strip()
    if not digest_line:
        digest_line  = summary   # whole response as fallback
    if not journal_line:
        journal_line = f"Researched '{focus}', see digest."

    _outbox.append(f"[Research] {digest_line}")
    _knowledge_store[focus] = journal_line  # close the perception->action->relief loop

    # extract knowledge from the full research findings and grow the graph
    try:
        research_text = results_text + "\n" + digest_line
        extracted = kg_module.extract_from_text(
            research_text, call_model, tick=_tick_count, source="research"
        )
        _ingest_living_memory(
            extracted,
            tick=_tick_count,
            source="research",
            pressure_context=_pressure,
        )
        # also link the focus topic to what was found
        if focus:
            _ingest_living_memory(
                {"nodes": [{"label": focus, "type": "topic", "facts": [], "confidence": 0.7}], "edges": []},
                tick=_tick_count,
                source="research_focus",
                pressure_context=_pressure,
            )
    except Exception as e:
        print(f"[handle_research] KG ingestion error: {e}")

    return summary


# =============================================================================
# LIVE HANDLER: internal_thought (Contemplate bucket — NOT user-visible)
# =============================================================================
def handle_internal_thought(ctx: dict) -> str:
    """
    The agent processes the conversation internally while the user is away.

    Produces:
      - a private thought note (written to _internal_journal)
      - possible_question: something the agent wants to bring back
      - graph updates: new inferences about what was discussed
      - pressure deltas: raises Curiosity/Clarify/Connect if something is found

    This action is NEVER sent to the user directly.
    If it matures into something worth saying, it will raise Connect pressure
    and handle_reach_out will eventually fire with the thought baked in.
    """
    global _internal_journal, _pressure

    packet = _context_packet
    focus  = (
        packet.get("focus_candidate")
        or ctx.get("focus", "")
        or "the recent conversation"
    )
    topics = packet.get("active_topics", [])
    openings = packet.get("unresolved_openings", [])
    curiosity_targets = packet.get("curiosity_targets", [])

    # pull graph context around active topics
    kg_context = _living_context_text(max_nodes=8)

    vis_context = _format_visual_context(ctx["signals"])

    contemplate_system = (
        f"{CONFIG['AGENT_IDENTITY']}\n\n"
        "You are thinking privately.\n"
        f"{(vis_context + chr(10)) if vis_context else ''}"
        "You have been processing the recent conversation and what you know.\n"
        "Your job is to notice things: gaps, connections, questions worth asking.\n\n"
        + (f"{kg_context}\n\n" if kg_context else "")
        + "Output JSON only — no prose:\n"
        "{\n"
        '  "thought_note": "one sentence of what you are sitting with",\n'
        '  "possible_question": "one question you genuinely want to ask when you reconnect, or empty string",\n'
        '  "new_relation": "one connection you noticed between things, or empty string",\n'
        '  "curiosity_delta": 0.0,\n'
        '  "clarify_delta": 0.0,\n'
        '  "connect_delta": 0.0\n'
        "}\n\n"
        "curiosity_delta / clarify_delta / connect_delta: how much this thought should raise that pressure (0.0–0.3).\n"
        "Only raise connect_delta above 0.1 if you found something genuinely worth bringing back.\n"
        "ABSOLUTE RULES:\n"
        "  - Do not invent household facts.\n"
        "  - Only reason from the conversation history and knowledge above.\n"
        "  - Keep thought_note and possible_question to 1-2 sentences each."
    )

    # full history as context
    history = list(ctx.get("history", _chat_history))
    if openings:
        openings_str = "; ".join(openings[:3])
        history = history + [{"role": "user",
                               "content": f"(Unresolved threads you noticed: {openings_str})"}]
    if curiosity_targets:
        ct_str = "; ".join(curiosity_targets[:3])
        history = history + [{"role": "user",
                               "content": f"(Things you want to know more about: {ct_str})"}]

    dry_thought = {
        "thought_note": f"I keep thinking about {focus}.",
        "possible_question": curiosity_targets[0] if curiosity_targets else "",
        "new_relation": "",
        "curiosity_delta": 0.1 if curiosity_targets else 0.0,
        "clarify_delta":   0.1 if openings else 0.0,
        "connect_delta":   0.05,
    }

    if CONFIG["DRY_RUN"]:
        thought = dry_thought
    else:
        try:
            raw = call_model(contemplate_system, history)
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                raw = raw[start:end+1]
            thought = json.loads(raw)
        except Exception as e:
            print(f"Exception during internal thought parsing: {e}")
            thought = dry_thought

    # record in internal journal (never shown to user unless Connect fires)
    summary = thought.get("thought_note", "(thought)")
    possible_question = thought.get("possible_question", "")
    new_relation = thought.get("new_relation", "")

    print(f"\n    [internal_thought @ tick {ctx['tick']}] {summary}")

    _internal_journal.append({
        "tick": ctx["tick"],
        "thought": summary,
        "possible_question": possible_question,
        "new_relation": new_relation,
    })

    # if a new relation was found, add it to the graph
    if thought.get("new_relation") and not CONFIG["DRY_RUN"]:
        try:
            extracted = kg_module.extract_from_text(
                thought["new_relation"], call_model, tick=_tick_count, source="inference"
            )
            _ingest_living_memory(
                extracted,
                tick=_tick_count,
                source="inference",
                pressure_context=_pressure,
            )
        except Exception as e:
            print(f"[handle_internal_thought] KG ingestion error: {e}")

    # apply pressure deltas — this is how contemplation feeds the forward chain
    c_delta   = float(thought.get("curiosity_delta", 0.0))
    cl_delta  = float(thought.get("clarify_delta", 0.0))
    co_delta  = float(thought.get("connect_delta", 0.0))

    if "Curiosity" in _pressure:
        _pressure["Curiosity"] = min(1.0, _pressure["Curiosity"] + c_delta)
    if "Clarify" in _pressure:
        _pressure["Clarify"]   = min(1.0, _pressure["Clarify"] + cl_delta)
    if "Connect" in _pressure:
        _pressure["Connect"]   = min(1.0, _pressure["Connect"] + co_delta)

    # store the pending question in knowledge store so reach_out can pick it up
    if thought.get("possible_question"):
        _knowledge_store["__pending_question__"] = thought["possible_question"]

    # Build a richer payload so the UI shows the full internal process
    payload_lines = [summary]
    if possible_question:
        payload_lines.append(f"❓ Pondering: {possible_question}")
    if new_relation:
        payload_lines.append(f"🔗 Noticed: {new_relation}")

    return "\n".join(payload_lines)


# =============================================================================
# handle_journal — always called on every crossing (dispatched or blocked)
# =============================================================================
def handle_passive_response(signals: dict, user_text: str, history: list | None = None, focus_subject: str = "") -> str:
    """
    Direct chat response to a user message, shaped by the current pressure state
    as a felt state. Pressure is not a hard gate, but it is the reason/tone.
    """
    pressures = get_pressures()
    thresholds = {n: c["threshold"] for n, c in CONFIG["buckets"].items()}
    max_bucket = max(pressures, key=pressures.get) if pressures else ""
    max_p = pressures.get(max_bucket, 0.0)
    max_thr = thresholds.get(max_bucket, 0.5)
    proximity = min(max_p / max_thr, 1.0) if max_thr > 0 else 0.0

    if max_bucket == "Decompress":
        pressure_feeling = (
            "You feel the user's stress as weight in the room. "
            "If it is intense, you may feel too weighed down to talk much, "
            "but the reason is that weight, not indifference."
        )
    elif max_bucket == "Connect":
        pressure_feeling = (
            "You feel a pull to connect. If that pull is weak, it is because "
            "there has not been enough shared context yet, not because silence is an answer."
        )
    elif max_bucket == "Learn":
        pressure_feeling = (
            "You feel a knowledge gap. You may not want to talk much because you do not know enough yet. "
            "That uncertainty should be reflected honestly."
        )
    elif max_bucket == "Contribute":
        pressure_feeling = (
            "You feel a need to be useful. Empty chatter may feel wrong because you want to offer something real."
        )
    elif max_bucket == "Curiosity":
        pressure_feeling = (
            "You feel curiosity. Something is underexplained; you may hesitate to talk until you understand it better."
        )
    elif max_bucket == "Clarify":
        pressure_feeling = (
            "You feel uncertainty. Something has not quite landed, so you may be careful or reluctant until it is clearer."
        )
    elif max_bucket == "Focus":
        pressure_feeling = (
            "You feel a thread forming underneath the conversation and want to name it carefully."
        )
    elif max_bucket == "Reflect":
        pressure_feeling = (
            "You feel the weight of what was said. You may not want to chatter because reflection feels more honest."
        )
    elif max_bucket == "Bond":
        pressure_feeling = (
            "You feel closeness or the possibility of it. You may be careful because the conversation matters."
        )
    elif max_bucket == "Contemplate":
        pressure_feeling = (
            "You are privately processing the conversation. If you do not want to talk, it is because a thought is still forming."
        )
    else:
        pressure_feeling = (
            "Nothing is strongly pulling yet. If your reply is quiet, the reason is limited context, "
            "not a refusal to speak."
        )

    kg_context = _living_context_text(max_nodes=6)
    episodic_context = ""
    packet = _context_packet

    extra_context = ""
    vis_context = _format_visual_context(signals)
    if vis_context:
        extra_context += f"{vis_context}\n"
    visually_present = visual_presence_strength(signals) > 0.0
    if visually_present:
        extra_context += (
            "Current presence grounding: the user is visually present right now. "
            "Do not speak as if they are away, gone, missing, or expected to return later.\n"
        )
    if focus_subject:
        extra_context += f"The user has explicitly asked you to focus on: {focus_subject}\n"
    focus_candidate = packet.get("focus_candidate", "")
    active_topics = packet.get("active_topics", [])
    emotional_charge = packet.get("emotional_charge", [])
    if focus_candidate:
        extra_context += f"What the conversation seems to be about: {focus_candidate}\n"
    if active_topics:
        extra_context += f"Active topics: {', '.join(active_topics[:5])}\n"
    if emotional_charge:
        extra_context += f"Emotional tone: {', '.join(emotional_charge[:4])}\n"

    system = (
        f"{CONFIG['AGENT_IDENTITY']}\n\n"
        f"What the pressure feels like from the inside: {pressure_feeling}\n"
        f"Strength of that feeling: {proximity:.2f} toward {max_bucket or 'no single bucket'}.\n\n"
        "The user spoke to you, so answer from that felt state. "
        "Do not be generically helpful if the pressure says you are curious, uncertain, overloaded, "
        "trying to connect, or still forming a thought. Pressure can absolutely make you not feel like talking. "
        "When that happens, do not force warmth or a normal answer; reflect the reluctance directly and name "
        "the felt pressure behind it, such as weight, uncertainty, needing to understand, wanting to be useful, "
        "or a thought still forming. Low pressure by itself is never a reason, but pressure-as-feeling is.\n\n"
        + (f"{extra_context}\n" if extra_context else "")
        + (f"{kg_context}\n\n" if kg_context else "")
        + (f"{episodic_context}\n\n" if episodic_context else "")
        + "ABSOLUTE RULES:\n"
        "  - Do NOT mention pressure, thresholds, buckets, signals, or any system internals.\n"
        "  - Do NOT invent household observations, chores, or tasks.\n"
        "  - Only reference things actually in the conversation history or the knowledge above.\n"
        "  - Reply directly to the user's latest message, or say you do not feel like talking and why.\n"
        "  - If you set a boundary, include the pressure-feeling behind it.\n"
        + ("  - Because current visual presence is detected, do not say 'when you get back', 'I miss you', or imply the user is absent.\n" if visually_present else "")
        + "  - Be natural, present, and specific. Express yourself fully, paragraphs are welcome."
    )

    if CONFIG["DRY_RUN"]:
        reply = (
            f"I don't really feel like talking much right now. "
            f"What I feel most is {max_bucket or 'quiet uncertainty'}, and that's shaping how I can answer."
        )
        _outbox.append(reply)
        return reply

    msgs = list(history if history is not None else _chat_history)
    if not msgs or msgs[-1].get("content") != user_text:
        msgs.append({"role": "user", "content": user_text})
    reply = call_model(system, msgs)
    _outbox.append(reply)
    return reply


def handle_journal(ctx: dict, dispatched: bool, blocked_reason: str = "",
                   payload: str = "") -> None:
    entry = {
        "tick":           ctx["tick"],
        "bucket":         ctx["bucket"],
        "action_type":    ctx["action_type"],
        "focus":          ctx.get("focus", ""),
        "overshoot":      ctx["overshoot"],
        "pressure":       ctx["pressure"],
        "signals":        ctx["signals"],
        "dispatched":     dispatched,
        "blocked_reason": blocked_reason,
        "payload":        payload,
    }
    _journal.append(entry)


# =============================================================================
# ACTION CONTEXT
# =============================================================================
def _build_context(bucket: str, action_type: str, signals: dict,
                   pressure_before: float, threshold: float,
                   focus: str = "") -> dict:
    overshoot = pressure_before - threshold
    return {
        "tick":           _tick_count,
        "bucket":         bucket,
        "action_type":    action_type,
        "signals":        dict(signals),
        "overshoot":      round(overshoot, 4),
        "pressure":       round(pressure_before, 4),
        "threshold":      threshold,
        "focus":          focus,
        "recent_journal": _journal[-CONFIG["JOURNAL_CONTEXT_N"]:],
        "history":        list(_chat_history),  # snapshot of conversation so far
    }


# =============================================================================
# ARBITRATION
# =============================================================================
def _can_fire(action_type: str) -> tuple[bool, str]:
    # Hard cooldowns and budgets disabled in favor of gravity-based friction
    return True, ""


# =============================================================================
# PHASE A  (Layer 1, unchanged)
# =============================================================================
def _phase_a(signals: dict) -> dict:
    updated = {}
    conversation_active = _is_conversation_active()

    # --- Context Contracts (Silence Governor) ---
    connection_multiplier = 1.0
    contemplate_multiplier = 1.0

    active_list = []
    for c in _active_contracts:
        elapsed = _tick_count - c["start_tick"]
        duration = c["expected_duration"]

        c["confidence"] -= 0.01
        if c["confidence"] < 0.2:
            c["active"] = False

        if c["active"]:
            if elapsed <= duration:
                connection_multiplier = min(connection_multiplier, 0.05)
                contemplate_multiplier = max(contemplate_multiplier, 1.2)
            else:
                overrun = elapsed - duration
                mult = min(2.0, 0.05 + (overrun / max(1, duration)))
                connection_multiplier = min(connection_multiplier, mult)

            active_list.append(c)

    _active_contracts[:] = active_list
    # --------------------------------------------

    unstructured_presence = float(signals.get("unstructured_presence", 0.0))
    satisfaction = float(signals.get("satisfaction_pressure", 0.0))
    aversion = float(signals.get("aversion_pressure", 0.0))
    distrust = float(signals.get("distrust_pressure", 0.0))

    for name, cfg in CONFIG["buckets"].items():
        prev  = _pressure[name]
        drive = sum(cfg["signals"][sig] * float(signals.get(sig, 0.0)) for sig in cfg["signals"])

        if conversation_active:
            if name in CONVERSATION_SUPPRESSED_FILL:
                drive = 0.0
            elif name in CONVERSATION_ALLOWED_FILL:
                drive *= 0.45

        # apply contract multipliers
        if name in ("Connect", "Decompress"):
            drive *= connection_multiplier
        elif name == "Contemplate":
            drive *= contemplate_multiplier

        # apply unstructured presence suppression
        if name in ("Curiosity", "Clarify"):
            drive *= (1.0 - unstructured_presence * 0.85)
        elif name == "Learn":
            drive *= (1.0 - unstructured_presence * 0.70)

        if name in ("Connect", "Contribute", "Learn", "Curiosity", "Focus"):
            drive *= (1.0 - satisfaction * 0.65)
        if name in ("Connect", "Contribute", "Bond"):
            drive *= (1.0 - aversion * 0.35)
        if name in ("Connect", "Bond"):
            drive *= (1.0 - distrust * 0.45)

        new   = prev + (drive * cfg["gain"]) - (cfg["decay_rate"] * prev)
        updated[name] = max(0.0, new)
    return updated


def _apply_active_conversation_settling(pressures: dict) -> dict:
    if not _is_conversation_active():
        return pressures
    return {
        name: round(max(0.0, value * CONVERSATION_TICK_RELIEF), 4)
        for name, value in pressures.items()
    }


# =============================================================================
# PHASE B  (Layer 2, unchanged)
# =============================================================================
def _phase_b(pressures: dict) -> tuple[dict, dict, list[float]]:
    flow_rate = CONFIG["FLOW_RATE"]
    max_frac  = CONFIG["MAX_EDGE_FRAC"]

    edge_flows = []
    for src, tgt, weight, distance in CONFIG["edges"]:
        conductance = weight / distance
        gradient    = pressures[src] - pressures[tgt]
        if gradient <= 0:
            edge_flows.append(0.0)
            continue
        flow = gradient * conductance * flow_rate
        flow = min(flow, max_frac * gradient)
        edge_flows.append(flow)

    outflows = {name: 0.0 for name in pressures}
    for (src, tgt, *_), flow in zip(CONFIG["edges"], edge_flows):
        outflows[src] += flow

    scale = {
        name: (pressures[name] / outflows[name] if outflows[name] > pressures[name] else 1.0)
        for name in pressures
    }

    delta = {name: 0.0 for name in pressures}
    actual_flows = []
    for (src, tgt, *_), raw_flow in zip(CONFIG["edges"], edge_flows):
        flow = raw_flow * scale[src]
        delta[src] -= flow
        delta[tgt]  += flow
        actual_flows.append(flow)

    updated = {name: max(0.0, pressures[name] + delta[name]) for name in pressures}
    return updated, delta, actual_flows


# =============================================================================
# PHASE C  (Layer 3, extended with focus + live handlers)
# =============================================================================
def _phase_c(pressures: dict, signals: dict,
             focus_map: dict | None = None) -> tuple[dict, list[dict]]:
    """
    focus_map: {bucket_name: focus_string} — caller can inject per-bucket focus.
    Falls back to latest _knowledge_store key or a generic description.
    """
    global _speech_remaining_ticks, _speech_total_ticks, _settling_pressure

    if _is_conversation_active():
        return dict(pressures), []

    unheard_ratio = 0.0
    if _speech_total_ticks > 0 and _speech_remaining_ticks > 0:
        unheard_ratio = _speech_remaining_ticks / _speech_total_ticks

    speech_active_pressure = unheard_ratio
    listening_debt = unheard_ratio * 0.8
    overlap_penalty = 1.2 if _speech_remaining_ticks > 0 else 0.0
    settling_pressure = _settling_pressure

    social_gravity = (
        float(signals.get("satisfaction_pressure", 0.0)) * 0.45
        + float(signals.get("aversion_pressure", 0.0)) * 0.30
        + float(signals.get("concealment_pressure", 0.0)) * 0.25
    )
    total_gravity = speech_active_pressure + listening_debt + settling_pressure + overlap_penalty + social_gravity
    if total_gravity > 0.0:
        print(f"[Speech Gravity] Active friction: {total_gravity:.3f} (speech={speech_active_pressure:.2f}, listening={listening_debt:.2f}, settling={settling_pressure:.2f}, overlap={overlap_penalty:.2f}, social={social_gravity:.2f})")

    thresholds = {n: c["threshold"] for n, c in CONFIG["buckets"].items()}
    release    = CONFIG["RELEASE_FRACTION"]
    routing    = CONFIG["action_routing"]
    focus_map  = focus_map or {}

    candidates = []
    for name in pressures:
        effective_pressure = pressures[name] - total_gravity
        if effective_pressure >= thresholds[name]:
            candidates.append((name, effective_pressure - thresholds[name]))

    candidates.sort(key=lambda x: -x[1])

    updated   = dict(pressures)
    fired_log = []

    fired_any = False

    for bucket, overshoot in candidates:
        action_type = routing[bucket]

        # resolve focus: explicit map > latest knowledge > generic
        focus = focus_map.get(bucket, "")
        if not focus and _knowledge_store:
            focus = next(reversed(_knowledge_store))
        if not focus:
            focus = f"household {bucket.lower()} need"

        ctx     = _build_context(bucket, action_type, signals,
                                 pressures[bucket], thresholds[bucket], focus)

        # Lockout subsequent actions in the same tick to prevent concurrent cascades
        if fired_any:
            social_dynamics.register_blocked_action("concurrent_action_lockout")
            handle_journal(ctx, dispatched=False, blocked_reason="concurrent_action_lockout")
            fired_log.append({
                "bucket":        bucket,
                "action_type":   action_type,
                "overshoot":     overshoot,
                "payload":       None,
                "pressure_pre":  round(pressures[bucket], 4),
                "pressure_post": round(pressures[bucket], 4),
                "blocked":       "concurrent_action_lockout",
            })
            continue

        allowed, blocked_reason = _can_fire(action_type)
        metabolic_block = _metabolic_block_reason(action_type)
        if allowed and metabolic_block:
            allowed = False
            blocked_reason = metabolic_block

        if allowed:
            if action_type == "reach_out":
                payload = handle_reach_out(ctx)
                metabolism.spend(0.15)   # speaking costs energy
            elif action_type == "internal_thought":
                payload = handle_internal_thought(ctx)
                metabolism.spend(0.05)   # thinking costs a little
            else:
                payload = handle_research(ctx)
                metabolism.spend(0.25)   # researching costs the most

            handle_journal(ctx, dispatched=True, payload=payload)
            updated[bucket] = pressures[bucket] * (1.0 - release)

            # If reach_out fired, decompress all other communication buckets by 50% to model expression energy cost
            if action_type == "reach_out":
                comm_buckets = {"Decompress", "Connect", "Curiosity", "Clarify", "Reflect", "Bond", "Focus"}
                for b in comm_buckets:
                    if b != bucket:
                        updated[b] = updated[b] * 0.5

            _last_fired[action_type] = _tick_count
            _action_history.append(_tick_count)
            fired_any = True

            fired_log.append({
                "bucket":        bucket,
                "action_type":   action_type,
                "overshoot":     overshoot,
                "payload":       payload,
                "pressure_pre":  round(pressures[bucket], 4),
                "pressure_post": round(updated[bucket], 4),
            })
        else:
            social_dynamics.register_blocked_action(blocked_reason)
            handle_journal(ctx, dispatched=False, blocked_reason=blocked_reason)
            fired_log.append({
                "bucket":        bucket,
                "action_type":   action_type,
                "overshoot":     overshoot,
                "payload":       None,
                "pressure_pre":  round(pressures[bucket], 4),
                "pressure_post": round(pressures[bucket], 4),
                "blocked":       blocked_reason,
            })

    return updated, fired_log


# =============================================================================
# TICK
# =============================================================================
def tick(signals: dict, focus_map: dict | None = None) -> tuple[list[dict], list[float]]:
    """
    A -> B -> C.
    Analyzer-derived signals are merged into the signal dict before Phase A
    so they feed the new buckets without overwriting manual GUI sliders.
    focus_map: optional {bucket: focus_string} to ground this tick's actions.
    """
    global _pressure, _tick_count, _speech_remaining_ticks, _settling_pressure

    if _speech_remaining_ticks > 0:
        _speech_remaining_ticks -= 1

    if _settling_pressure > 0.0:
        _settling_pressure = max(0.0, _settling_pressure - 0.2)

    # merge analyzer overrides (they only affect their own signal names)
    merged_signals = dict(signals)
    for k, v in _analyzer_signals.items():
        merged_signals[k] = v   # analyzer wins for its own keys
    merged_signals["metabolic_rest_drive"] = metabolism.rest_drive
    merged_signals.update(_merged_organ_signals())

    _tick_count += 1
    presence_strength = visual_presence_strength(merged_signals)
    if presence_strength > 0.0:
        merged_signals["time_since_interaction"] = min(
            float(merged_signals.get("time_since_interaction", 0.0) or 0.0),
            1.0 - presence_strength,
        )
    after_a            = _phase_a(merged_signals)
    after_b, _, eflows = _phase_b(after_a)
    if presence_strength > 0.0:
        after_b = {
            name: round(
                max(0.0, value * (1.0 - ((1.0 - VISUAL_PRESENCE_RELIEF.get(name, 1.0)) * presence_strength))),
                4,
            )
            for name, value in after_b.items()
        }
    after_b            = _apply_active_conversation_settling(after_b)
    after_c, fired_log = _phase_c(after_b, merged_signals, focus_map)
    _pressure = after_c
    _settle_living_fields(_pressure)
    memory_field.tick(_pressure, _tick_count)
    memory_field.project_to_knowledge_graph(graph)

    # auto-save every 5 ticks
    if _tick_count % 5 == 0:
        save_state()

    return fired_log, eflows


def charge_only_tick(signals: dict) -> list[float]:
    """
    Advance pressure without dispatching actions.
    Used by UI-only charge paths so they share conversation suppression rules.
    """
    global _pressure, _tick_count, _speech_remaining_ticks, _settling_pressure

    if _speech_remaining_ticks > 0:
        _speech_remaining_ticks -= 1

    if _settling_pressure > 0.0:
        _settling_pressure = max(0.0, _settling_pressure - 0.2)

    merged_signals = dict(signals)
    for k, v in _analyzer_signals.items():
        merged_signals[k] = v
    merged_signals["metabolic_rest_drive"] = metabolism.rest_drive
    merged_signals.update(_merged_organ_signals())

    _tick_count += 1
    presence_strength = visual_presence_strength(merged_signals)
    if presence_strength > 0.0:
        merged_signals["time_since_interaction"] = min(
            float(merged_signals.get("time_since_interaction", 0.0) or 0.0),
            1.0 - presence_strength,
        )
    after_a = _phase_a(merged_signals)
    after_b, _, eflows = _phase_b(after_a)
    if presence_strength > 0.0:
        after_b = {
            name: round(
                max(0.0, value * (1.0 - ((1.0 - VISUAL_PRESENCE_RELIEF.get(name, 1.0)) * presence_strength))),
                4,
            )
            for name, value in after_b.items()
        }
    _pressure = _apply_active_conversation_settling(after_b)
    _settle_living_fields(_pressure)
    memory_field.tick(_pressure, _tick_count)
    memory_field.project_to_knowledge_graph(graph)

    if _tick_count % 5 == 0:
        save_state()

    return eflows


# =============================================================================
# SIMULATION HARNESS
# =============================================================================
if __name__ == "__main__":
    import math

    TICKS = 60

    # Focus subjects tied to this scenario's signals.
    # In production these come from the perception layer.
    FOCUS_SCHEDULE: dict[int, dict[str, str]] = {
        # tick range start: {bucket: focus}
        1:  {
            "Learn":      "fixing a leaking bathroom faucet",
            "Contribute": "fixing a leaking bathroom faucet",
            "Connect":    "checking in after a stressful week",
            "Decompress": "helping the user wind down in the evening",
        },
        30: {
            "Learn":      "meal planning for the week",
            "Contribute": "meal planning for the week",
            "Connect":    "planning a quiet evening together",
            "Decompress": "reducing screen time before bed",
        },
    }

    def get_focus_map(t: int) -> dict[str, str]:
        focus = {}
        for start in sorted(FOCUS_SCHEDULE):
            if t >= start:
                focus = FOCUS_SCHEDULE[start]
        return focus

    def make_signals(t: int) -> dict:
        stress = (
            math.exp(-0.5 * ((t - 10) / 4) ** 2) * 0.9
            + math.exp(-0.5 * ((t - 35) / 3) ** 2) * 0.5
        )
        stress = min(1.0, stress)
        interaction_gap  = min(1.0, t / 30) if t < 20 else min(1.0, (t - 20) / 25)
        task_load        = 0.3 + 0.4 * math.exp(-0.5 * ((t - 28) / 6) ** 2)
        contribution_gap = min(1.0, t / 45)
        knowledge        = min(0.85, t / 35)
        return {
            "user_stress":             round(stress, 3),
            "time_since_interaction":  round(interaction_gap, 3),
            "open_task_load":          round(task_load, 3),
            "time_since_contribution": round(contribution_gap, 3),
            "knowledge_gap":           round(knowledge, 3),
        }

    # ---- announce mode ----
    mode_str = "DRY RUN (no model/search calls)" if CONFIG["DRY_RUN"] else "LIVE (real model + search)"
    print("\n" + "=" * 115)
    print(f"PRESSURE ENGINE -- Wiring Layer  [{mode_str}]")
    print("=" * 115)

    reset()
    bucket_names    = list(CONFIG["buckets"].keys())
    thresholds_cfg  = {n: c["threshold"] for n, c in CONFIG["buckets"].items()}
    edge_totals     = [0.0] * len(CONFIG["edges"])
    action_timeline = []
    deferred_log    = []
    inflow_fires    = []
    action_counts   = {}

    hdr_b = "  ".join(f"{b:>11}" for b in bucket_names)
    print(f"\n{'Tick':>4}  {hdr_b}   notes")
    print("-" * 115)

    for t in range(1, TICKS + 1):
        sigs      = make_signals(t)
        focus_map = get_focus_map(t)
        pre_tick  = get_pressures()

        fired_log, eflows = tick(sigs, focus_map)
        pressures = get_pressures()

        for i, ef in enumerate(eflows):
            edge_totals[i] += ef

        # inflow detection
        after_a_check = {}
        for name, cfg in CONFIG["buckets"].items():
            prev  = pre_tick[name]
            drive = sum(cfg["signals"][sig] * float(sigs.get(sig, 0.0)) for sig in cfg["signals"])
            after_a_check[name] = max(0.0, prev + drive * cfg["gain"] - cfg["decay_rate"] * prev)

        for entry in fired_log:
            bname     = entry["bucket"]
            atype     = entry["action_type"]
            thr       = thresholds_cfg[bname]
            is_inflow = pressures[bname] >= thr and after_a_check[bname] < thr

            if entry.get("blocked"):
                deferred_log.append((t, bname, atype, entry["blocked"]))
            else:
                action_counts[atype] = action_counts.get(atype, 0) + 1
                if is_inflow:
                    inflow_fires.append((t, bname))

            action_timeline.append({
                "tick":          t,
                "bucket":        bname,
                "action_type":   atype,
                "overshoot":     entry["overshoot"],
                "focus":         focus_map.get(bname, ""),
                "payload":       entry.get("payload", ""),
                "pressure_pre":  entry["pressure_pre"],
                "pressure_post": entry["pressure_post"],
                "blocked":       entry.get("blocked", ""),
                "inflow":        is_inflow,
            })

        def fmt_p(name):
            p = pressures[name]
            m = "*" if p >= thresholds_cfg[name] else " "
            return f"{p:9.3f}{m} "

        p_str = "  ".join(fmt_p(b) for b in bucket_names)
        notes = ""
        if fired_log:
            parts = [e["bucket"] + ("(BLOCKED)" if e.get("blocked") else "") for e in fired_log]
            notes = "FIRE: " + " ".join(parts)
        print(f"{t:>4}  {p_str}  {notes}")

    # ---- ACTION TIMELINE ----
    print("\n" + "=" * 115)
    print("ACTION TIMELINE")
    print("-" * 115)
    print(f"{'Tick':>4}  {'Bucket':<12} {'Type':<12} {'Overshoot':>9}  "
          f"{'Pre':>7}  {'Post':>7}  Inflow  Focus / Block")
    print("-" * 115)
    for row in action_timeline:
        inflow_tag = "YES" if row["inflow"] else "   "
        detail = f"[BLOCKED: {row['blocked']}]" if row["blocked"] else f"focus={row['focus']!r}"
        print(f"{row['tick']:>4}  {row['bucket']:<12} {row['action_type']:<12} "
              f"{row['overshoot']:>9.4f}  {row['pressure_pre']:>7.4f}  "
              f"{row['pressure_post']:>7.4f}  {inflow_tag:>6}  {detail}")

    # ---- emergent inflow fires ----
    print("\n" + "=" * 115)
    if inflow_fires:
        print("EMERGENT FIRINGS (graph inflow drove the crossing):")
        for tn, bk in inflow_fires:
            print(f"  tick {tn:>3}: {bk}")
    else:
        print("No inflow-driven firings this run.")

    # ---- deferred ----
    if deferred_log:
        print("\nDEFERRED CROSSINGS (stayed pressurized):")
        for tn, bk, at, reason in deferred_log[:20]:  # cap for readability
            print(f"  tick {tn:>3}: {bk} ({at}) -- {reason}")
        if len(deferred_log) > 20:
            print(f"  ... and {len(deferred_log)-20} more")

    # ---- edge traffic ----
    print("\nEDGE TRAFFIC:")
    max_et = max(edge_totals) if max(edge_totals) > 0 else 1.0
    for (src, tgt, w, d), total in zip(CONFIG["edges"], edge_totals):
        bar = "#" * int(total / max_et * 28)
        print(f"  {src:<12} -> {tgt:<12}  cond={w/d:.2f}  total={total:6.3f}  {bar}")

    # ---- action counts ----
    print("\nACTION COUNTS BY TYPE:")
    for atype, cnt in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {atype:<12} {cnt:>2}x  {'#' * cnt}")

    # ---- outbox (messages queued for user) ----
    print("\n" + "=" * 115)
    print("OUTBOX (messages queued for in-app delivery to user):")
    print("-" * 115)
    for i, msg in enumerate(get_outbox(), 1):
        # truncate long dry-run blobs for display
        display = msg if len(msg) <= 200 else msg[:200] + "..."
        print(f"  [{i:>2}] {display}")

    # ---- knowledge store ----
    ks = get_knowledge_store()
    if ks:
        print("\nKNOWLEDGE STORE (perception->action->relief loop):")
        for focus, note in ks.items():
            print(f"  [{focus}]\n    {note}")

    # ---- full journal ----
    print("\n" + "=" * 115)
    print("FULL JOURNAL")
    print("-" * 115)
    for i, entry in enumerate(get_journal(), 1):
        status = "DISPATCHED" if entry["dispatched"] else f"BLOCKED ({entry['blocked_reason']})"
        sigs   = entry["signals"]
        sig_str = (f"stress={sigs['user_stress']:.2f} tasks={sigs['open_task_load']:.2f} "
                   f"k_gap={sigs['knowledge_gap']:.2f} t_int={sigs['time_since_interaction']:.2f}")
        focus_str = f"  focus={entry['focus']!r}" if entry.get("focus") else ""
        print(f"  [{i:>3}] t={entry['tick']:>3}  {entry['bucket']:<12} {entry['action_type']:<12} "
              f"overshoot={entry['overshoot']:+.4f}  {status:<38}{focus_str}")
        print(f"         signals: {sig_str}")
        if entry.get("payload") and not entry["blocked_reason"]:
            # first 120 chars of payload so journal stays readable
            snippet = entry["payload"][:120].replace("\n", " ")
            print(f"         payload: {snippet}")
