import json
import time
import hashlib
from dataclasses import dataclass, field
import knowledge_graph as kg_module

# ── data structures ───────────────────────────────────────────────────────────

@dataclass
class StateSnapshot:
    tick: int
    timestamp: float
    message_count: int
    last_user_message_hash: str
    last_assistant_message_hash: str
    graph_node_count: int
    graph_edge_count: int
    active_topics: frozenset[str]
    pressure_values: dict[str, float]
    analyzer_packet: dict
    recent_edges_added: list[tuple[str, str, str]]

@dataclass
class PatternRecord:
    pattern_id: str
    first_seen_tick: int
    last_seen_tick: int
    occurrences: int = 1
    confidence: float = 0.1
    decay: float = 0.0
    related_nodes: set[str] = field(default_factory=set)
    related_edges: list[tuple[str, str, str]] = field(default_factory=list)
    unresolved_count: int = 0
    example_differences: list[dict] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "id": self.pattern_id,
            "first_seen_tick": self.first_seen_tick,
            "last_seen_tick": self.last_seen_tick,
            "occurrences": self.occurrences,
            "confidence": round(self.confidence, 3),
            "decay": round(self.decay, 3),
            "related_nodes": list(self.related_nodes),
            "related_edges": self.related_edges,
            "unresolved_count": self.unresolved_count,
            "example_differences": self.example_differences
        }

# ── configuration ─────────────────────────────────────────────────────────────

CONFIG = {
    "pressure_threshold": 0.50,
    "confidence_increase_per_occurrence": 0.08,
    "confidence_decay_per_tick": 0.02,
    "max_confidence": 0.95,
    "min_confidence": 0.0,
    "max_example_differences": 5,
    "clarification_occurrences_threshold": 8,
    "clarification_confidence_min": 0.25,
    "clarification_confidence_max": 0.40,
    "clarification_stuck_ticks": 5
}

# ── state ─────────────────────────────────────────────────────────────────────

_previous_snapshot: StateSnapshot | None = None
_active_patterns: dict[str, PatternRecord] = {}
_recent_differences: list[dict] = []
_concept_pressure_max: float = 0.0
_tentative_count: int = 0

def reset():
    global _previous_snapshot, _active_patterns, _recent_differences, _concept_pressure_max, _tentative_count
    _previous_snapshot = None
    _active_patterns.clear()
    _recent_differences.clear()
    _concept_pressure_max = 0.0
    _tentative_count = 0

def get_state() -> dict:
    return {
        "recent_differences": _recent_differences[-5:],
        "active_patterns": [p.to_dict() for p in sorted(_active_patterns.values(), key=lambda x: -x.occurrences)],
        "concept_pressure": round(_concept_pressure_max, 3),
        "tentative_count": _tentative_count
    }

# ── core logic ────────────────────────────────────────────────────────────────

def _hash_string(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:8]

def capture_snapshot(tick: int, history: list[dict], graph: kg_module.KnowledgeGraph, pressures: dict, analyzer_packet: dict) -> StateSnapshot:
    user_msgs = [m["content"] for m in history if m.get("role") == "user"]
    asst_msgs = [m["content"] for m in history if m.get("role") == "assistant"]
    last_user = _hash_string(user_msgs[-1]) if user_msgs else ""
    last_asst = _hash_string(asst_msgs[-1]) if asst_msgs else ""
    
    # recent edges added in this tick
    recent_edges = [(e.source_id, e.relation, e.target_id) for e in graph.edges if e.tick == tick]
    
    return StateSnapshot(
        tick=tick,
        timestamp=time.time(),
        message_count=len(history),
        last_user_message_hash=last_user,
        last_assistant_message_hash=last_asst,
        graph_node_count=len(graph.nodes),
        graph_edge_count=len(graph.edges),
        active_topics=frozenset(analyzer_packet.get("active_topics", [])),
        pressure_values=dict(pressures),
        analyzer_packet=dict(analyzer_packet),
        recent_edges_added=recent_edges
    )

def compute_difference(curr: StateSnapshot, prev: StateSnapshot) -> dict:
    diff = {
        "tick": curr.tick,
        "nodes_added": curr.graph_node_count - prev.graph_node_count,
        "edges_added": curr.graph_edge_count - prev.graph_edge_count,
        "new_edges": curr.recent_edges_added,
        "topics_changed": list(curr.active_topics - prev.active_topics),
        "user_spoke": curr.last_user_message_hash != prev.last_user_message_hash,
        "asst_spoke": curr.last_assistant_message_hash != prev.last_assistant_message_hash,
    }
    return diff

def fingerprint_difference(diff: dict) -> str:
    # A canonical string for the shape of the diff
    parts = []
    if diff["user_spoke"]: parts.append("user_spoke")
    if diff["asst_spoke"]: parts.append("asst_spoke")
    if diff["nodes_added"] > 0: parts.append(f"+{diff['nodes_added']}nodes")
    if diff["edges_added"] > 0: parts.append(f"+{diff['edges_added']}edges")
    for t in sorted(diff["topics_changed"]):
        parts.append(f"topic:{t}")
    for src, rel, tgt in sorted(diff["new_edges"]):
        parts.append(f"edge:{rel}")
    
    if not parts:
        return "empty"
    return "|".join(parts)

def update_patterns(diff: dict, fingerprint: str, tick: int, graph: kg_module.KnowledgeGraph):
    if fingerprint == "empty":
        return
    
    if fingerprint in _active_patterns:
        pat = _active_patterns[fingerprint]
        pat.occurrences += 1
        pat.last_seen_tick = tick
        pat.confidence = min(CONFIG["max_confidence"], pat.confidence + CONFIG["confidence_increase_per_occurrence"])
        pat.decay = 0.0
        
        # update related edges/nodes
        for src, rel, tgt in diff["new_edges"]:
            pat.related_nodes.update([src, tgt])
            if (src, rel, tgt) not in pat.related_edges:
                pat.related_edges.append((src, rel, tgt))
                
        # check unresolvedness
        pat.unresolved_count = 0
        for node_id in pat.related_nodes:
            if node_id in graph.nodes and graph.nodes[node_id].status != "confirmed":
                pat.unresolved_count += 1
                
        if len(pat.example_differences) < CONFIG["max_example_differences"]:
            pat.example_differences.append(diff)
    else:
        pat = PatternRecord(
            pattern_id=fingerprint,
            first_seen_tick=tick,
            last_seen_tick=tick,
            occurrences=1,
            confidence=0.1,
            unresolved_count=0
        )
        for src, rel, tgt in diff["new_edges"]:
            pat.related_nodes.update([src, tgt])
            pat.related_edges.append((src, rel, tgt))
        pat.example_differences.append(diff)
        _active_patterns[fingerprint] = pat

def compute_concept_pressure(pat: PatternRecord) -> float:
    # gap_magnitude (approximated by number of related edges/topics in pattern)
    # recurrence (min(1.0, occurrences/5))
    # unresolvedness (unresolved_count/10)
    gap_mag = min(1.0, len(pat.related_edges) * 0.2 + 0.2)
    rec = min(1.0, pat.occurrences / 5.0)
    unres = min(1.0, max(1, pat.unresolved_count) / 10.0) # avoid zeroing out if just starting
    return gap_mag * rec * unres

def maybe_create_tentative_concept(pat: PatternRecord, graph: kg_module.KnowledgeGraph, tick: int):
    global _tentative_count
    pressure = compute_concept_pressure(pat)
    
    if pressure >= CONFIG["pressure_threshold"]:
        # Find a candidate label from the pattern (most frequent relation or node in the edges)
        if not pat.related_edges:
            return
            
        # simple heuristic: use the relation name if it repeats, or just pick one
        relations = [r for _, r, _ in pat.related_edges]
        if not relations:
            return
        # most common relation
        candidate_label = max(set(relations), key=relations.count)
        
        nid = kg_module._normalize(candidate_label)
        
        # Don't overwrite confirmed nodes
        if nid in graph.nodes and graph.nodes[nid].status == "confirmed":
            return
            
        # Map pressure [0.50 -> 0.25, 1.0 -> 0.40] for confidence
        # linear map: (pressure - 0.5) * (0.15 / 0.5) + 0.25
        conf = (pressure - 0.50) * 0.30 + 0.25
        conf = max(0.25, min(0.40, conf))
        
        facts = [
            f"Appears repeatedly in relation to: {', '.join(list(pat.related_nodes)[:3])}.",
            f"Created from recurring unresolved relationship pattern."
        ]
        
        if nid not in graph.nodes:
            node = graph.add_node(
                label=candidate_label,
                ntype="tentative_concept",
                facts=facts,
                confidence=conf,
                tick=tick,
                source="concept_formation"
            )
            node.status = "tentative"
            _tentative_count += 1
        elif graph.nodes[nid].status == "tentative":
            graph.nodes[nid].support_count += 1
            graph.nodes[nid].confidence = max(graph.nodes[nid].confidence, conf)

def test_concept(node: kg_module.Node, new_diff: dict, graph: kg_module.KnowledgeGraph, tick: int):
    # strengthen / weaken / merge / trigger clarification question
    nid = node.id
    
    # check new edges for support or contradiction
    for src, rel, tgt in new_diff["new_edges"]:
        if src == nid or tgt == nid or rel == node.label:
            if "not " in rel or "no " in rel:
                node.contradiction_count += 1
                node.confidence -= 0.05
            else:
                node.support_count += 1
                node.confidence += 0.05
                
    node.confidence = max(0.0, min(1.0, node.confidence))
    
    if node.confidence >= 0.70:
        node.status = "confirmed"
    elif node.confidence <= 0.0:
        node.status = "weakened"

def handle_decay(tick: int):
    # decay all patterns not seen this tick
    to_remove = []
    for fid, pat in _active_patterns.items():
        if pat.last_seen_tick < tick:
            pat.decay += CONFIG["confidence_decay_per_tick"]
            pat.confidence -= CONFIG["confidence_decay_per_tick"]
            if pat.confidence <= 0:
                to_remove.append(fid)
                
    for fid in to_remove:
        del _active_patterns[fid]

def check_clarification_trigger(knowledge_store: dict, tick: int):
    # If occurrences >= 8 and confidence is stuck 0.25–0.40 for > 5 ticks:
    for pat in _active_patterns.values():
        if pat.occurrences >= CONFIG["clarification_occurrences_threshold"]:
            if CONFIG["clarification_confidence_min"] <= pat.confidence <= CONFIG["clarification_confidence_max"]:
                if (tick - pat.last_seen_tick) <= 1: # recently active but stuck
                    # check if it's been stuck (approximated by high occurrences but low confidence)
                    relations = [r for _, r, _ in pat.related_edges]
                    if relations:
                        candidate_label = max(set(relations), key=relations.count)
                        nodes_str = ", ".join(list(pat.related_nodes)[:3])
                        q = f"I keep seeing '{candidate_label}' connected to {nodes_str}. Is {candidate_label} a property or relation there?"
                        
                        # Only push if we haven't recently pushed a pending question
                        if "__pending_question__" not in knowledge_store:
                            knowledge_store["__pending_question__"] = q

def tick(snapshot: StateSnapshot, graph: kg_module.KnowledgeGraph, tick_count: int, knowledge_store: dict) -> dict:
    global _previous_snapshot, _concept_pressure_max
    
    out_signals = {
        "concept_gap": 0.0,
        "pattern_recurrence": 0.0,
        "unresolved_pattern_pressure": 0.0
    }
    
    if _previous_snapshot is None:
        _previous_snapshot = snapshot
        return out_signals
        
    diff = compute_difference(snapshot, _previous_snapshot)
    _previous_snapshot = snapshot
    
    if not any(v for k,v in diff.items() if k not in ["tick", "user_spoke", "asst_spoke"]):
        # Nothing significant changed
        return out_signals
        
    _recent_differences.append(diff)
    
    fingerprint = fingerprint_difference(diff)
    update_patterns(diff, fingerprint, tick_count, graph)
    
    handle_decay(tick_count)
    
    _concept_pressure_max = 0.0
    max_recurrence = 0.0
    
    for pat in _active_patterns.values():
        cp = compute_concept_pressure(pat)
        if cp > _concept_pressure_max:
            _concept_pressure_max = cp
        
        rec = min(1.0, pat.occurrences / 5.0)
        if rec > max_recurrence:
            max_recurrence = rec
            
        maybe_create_tentative_concept(pat, graph, tick_count)
        
    # Test existing tentative concepts
    for nid, node in list(graph.nodes.items()):
        if getattr(node, "type", "") == "tentative_concept" and getattr(node, "status", "") == "tentative":
            test_concept(node, diff, graph, tick_count)
            
    check_clarification_trigger(knowledge_store, tick_count)
    
    # Populate signals
    out_signals["concept_gap"] = min(1.0, _concept_pressure_max * 0.8)
    out_signals["pattern_recurrence"] = max_recurrence
    out_signals["unresolved_pattern_pressure"] = min(1.0, _concept_pressure_max)
    
    return out_signals
