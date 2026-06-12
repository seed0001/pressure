"""
Knowledge Graph — the agent's growing model of the world.

Nodes: things the agent knows about (people, places, topics, objects, events).
Edges: relationships between them.

Everything comes from real sources only:
  - conversation (user tells the agent something)
  - research (agent searches and finds something)
  - inference (agent connects two known nodes)

Nothing is invented. Confidence tracks how certain each fact is.
The graph is queried to build grounded context for every response.
"""

import json
import re
import time

# ── data structures ───────────────────────────────────────────────────────────

class Node:
    __slots__ = ("id", "label", "type", "facts", "confidence",
                 "first_tick", "last_tick", "source", "status", "support_count", "contradiction_count")
    def __init__(self, label: str, ntype: str = "concept",
                 facts: list | None = None, confidence: float = 0.8,
                 tick: int = 0, source: str = "conversation"):
        self.id         = _normalize(label)
        self.label      = label
        self.type       = ntype          # person, place, topic, object, event, concept
        self.facts      = facts or []    # list of plain-English fact strings
        self.confidence = confidence
        self.first_tick = tick
        self.last_tick  = tick
        self.source     = source
        self.status     = None
        self.support_count = 0
        self.contradiction_count = 0

    def merge(self, other: "Node") -> None:
        """Absorb facts from another node about the same entity."""
        for f in other.facts:
            if f not in self.facts:
                self.facts.append(f)
        self.confidence = max(self.confidence, other.confidence)
        self.last_tick  = max(self.last_tick, other.last_tick)
        
        if other.type == "tentative_concept" and self.type != "tentative_concept":
            other.status = "merged"
            self.support_count += other.support_count
        elif other.type == "tentative_concept" and self.type == "tentative_concept":
            self.support_count += other.support_count
            self.contradiction_count += other.contradiction_count

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "type": self.type,
            "facts": self.facts, "confidence": round(self.confidence, 3),
            "first_tick": self.first_tick, "last_tick": self.last_tick,
            "source": self.source, "status": self.status,
            "support_count": self.support_count,
            "contradiction_count": self.contradiction_count
        }


class Edge:
    __slots__ = ("source_id", "target_id", "relation",
                 "weight", "confidence", "tick", "source")
    def __init__(self, source_id: str, target_id: str, relation: str,
                 weight: float = 1.0, confidence: float = 0.8,
                 tick: int = 0, source: str = "conversation"):
        self.source_id  = source_id
        self.target_id  = target_id
        self.relation   = relation
        self.weight     = weight
        self.confidence = confidence
        self.tick       = tick
        self.source     = source

    def to_dict(self) -> dict:
        return {
            "source": self.source_id, "target": self.target_id,
            "relation": self.relation, "weight": round(self.weight, 3),
            "confidence": round(self.confidence, 3),
            "tick": self.tick, "source": self.source,
        }


def _normalize(label: str) -> str:
    return re.sub(r"\s+", "_", label.strip().lower())


# ── graph ─────────────────────────────────────────────────────────────────────

class KnowledgeGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge]      = []

    def reset(self):
        self.nodes.clear()
        self.edges.clear()

    # ── write ──────────────────────────────────────────────────────────────

    def add_node(self, label: str, ntype: str = "concept",
                 facts: list | None = None, confidence: float = 0.8,
                 tick: int = 0, source: str = "conversation") -> Node:
        nid = _normalize(label)
        if nid in self.nodes:
            # Guard against overwriting a confirmed node with a tentative one
            existing = self.nodes[nid]
            if source == "concept_formation" and existing.source != "concept_formation":
                existing.support_count += 1
                return existing
            
            incoming = Node(label, ntype, facts or [], confidence, tick, source)
            self.nodes[nid].merge(incoming)
        else:
            self.nodes[nid] = Node(label, ntype, facts or [], confidence, tick, source)
        return self.nodes[nid]

    def get_tentative_concepts(self) -> list[dict]:
        return [node.to_dict() for node in self.nodes.values() if node.type == "tentative_concept"]

    def add_edge(self, src_label: str, tgt_label: str, relation: str,
                 weight: float = 1.0, confidence: float = 0.8,
                 tick: int = 0, source: str = "conversation") -> Edge | None:
        src_id = _normalize(src_label)
        tgt_id = _normalize(tgt_label)
        if src_id not in self.nodes or tgt_id not in self.nodes:
            return None
        # deduplicate: same src/tgt/relation → update weight
        for e in self.edges:
            if e.source_id == src_id and e.target_id == tgt_id and e.relation == relation:
                e.weight     = min(1.0, e.weight + 0.1)
                e.confidence = max(e.confidence, confidence)
                e.tick       = tick
                return e
        edge = Edge(src_id, tgt_id, relation, weight, confidence, tick, source)
        self.edges.append(edge)
        return edge

    def ingest(self, extracted: dict, tick: int, source: str = "conversation") -> None:
        """
        Apply a parsed extraction dict to the graph.
        Expected shape:
          {
            "nodes": [{"label": str, "type": str, "facts": [str], "confidence": float}],
            "edges": [{"source": str, "target": str, "relation": str, "confidence": float}]
          }
        """
        for n in extracted.get("nodes", []):
            self.add_node(
                label      = n.get("label", ""),
                ntype      = n.get("type", "concept"),
                facts      = n.get("facts", []),
                confidence = float(n.get("confidence", 0.8)),
                tick       = tick,
                source     = source,
            )
        for e in extracted.get("edges", []):
            src = e.get("source", "")
            tgt = e.get("target", "")
            rel = e.get("relation", "related to")
            if src and tgt:
                # ensure both nodes exist (may be mentioned only in an edge)
                if _normalize(src) not in self.nodes:
                    self.add_node(src, tick=tick, source=source)
                if _normalize(tgt) not in self.nodes:
                    self.add_node(tgt, tick=tick, source=source)
                self.add_edge(src, tgt, rel,
                              confidence=float(e.get("confidence", 0.7)),
                              tick=tick, source=source)

    # ── read ───────────────────────────────────────────────────────────────

    def neighbors(self, label: str) -> list[tuple[str, str, str]]:
        """Return [(neighbor_label, relation, direction)] for a node."""
        nid = _normalize(label)
        result = []
        for e in self.edges:
            if e.source_id == nid and e.target_id in self.nodes:
                result.append((self.nodes[e.target_id].label, e.relation, "out"))
            elif e.target_id == nid and e.source_id in self.nodes:
                result.append((self.nodes[e.source_id].label, e.relation, "in"))
        return result

    def relevant_context(self, topics: list[str], max_nodes: int = 8) -> str:
        """
        Return a plain-English summary of what the agent knows about the
        given topics, plus their direct neighbors. Used to ground model calls.
        """
        if not self.nodes:
            return ""

        seen_ids: set[str] = set()
        lines: list[str]   = []

        # seed from topic matches
        for topic in topics:
            nid = _normalize(topic)
            # fuzzy: also check if topic is a substring of any node id
            matches = [n for nid2, n in self.nodes.items()
                       if nid == nid2 or topic.lower() in n.label.lower()]
            for node in matches[:3]:
                if node.id in seen_ids:
                    continue
                seen_ids.add(node.id)
                fact_str = "; ".join(node.facts) if node.facts else "no facts yet"
                lines.append(f"  [{node.type}] {node.label}: {fact_str}")
                # include direct neighbors
                for neighbor_label, relation, direction in self.neighbors(node.label)[:4]:
                    neighbor_id = _normalize(neighbor_label)
                    if neighbor_id not in seen_ids:
                        seen_ids.add(neighbor_id)
                        n2 = self.nodes.get(neighbor_id)
                        n2_facts = ("; ".join(n2.facts[:2])) if n2 and n2.facts else ""
                        arrow = "->" if direction == "out" else "<-"
                        lines.append(
                            f"    {arrow} {relation} {arrow} {neighbor_label}"
                            + (f": {n2_facts}" if n2_facts else "")
                        )
                if len(seen_ids) >= max_nodes:
                    break
            if len(seen_ids) >= max_nodes:
                break

        if not lines:
            return ""
        return "What the agent already knows:\n" + "\n".join(lines)

    def summary_text(self, max_nodes: int = 20) -> str:
        """Full readable dump for debugging / journal."""
        if not self.nodes:
            return "(graph empty)"
        lines = [f"Nodes ({len(self.nodes)}), Edges ({len(self.edges)}):"]
        for node in sorted(self.nodes.values(), key=lambda n: -n.last_tick)[:max_nodes]:
            fact_str = "; ".join(node.facts[:3]) if node.facts else "—"
            lines.append(f"  {node.label} [{node.type}] conf={node.confidence:.2f}  {fact_str}")
        for e in sorted(self.edges, key=lambda e: -e.tick)[:15]:
            s = self.nodes.get(e.source_id)
            t = self.nodes.get(e.target_id)
            if s and t:
                lines.append(f"  {s.label} --[{e.relation}]--> {t.label}  w={e.weight:.2f}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }


# ── extraction ────────────────────────────────────────────────────────────────

EXTRACT_SYSTEM = """You are a knowledge extraction engine. Given a piece of text, extract entities and relationships.

Output ONLY valid JSON in exactly this shape — no prose, no markdown fences:
{
  "nodes": [
    {"label": "...", "type": "person|place|topic|object|event|concept", "facts": ["..."], "confidence": 0.0-1.0}
  ],
  "edges": [
    {"source": "...", "target": "...", "relation": "...", "confidence": 0.0-1.0}
  ]
}

Rules:
- Extract only what is explicitly stated. Do not infer or invent.
- "label" is the canonical name of the entity (proper noun or short phrase).
- "facts" are short plain-English statements directly supported by the text.
- "relation" is a short verb phrase (e.g. "lives in", "works at", "related to", "part of").
- Minimum confidence 0.5. Use 0.9+ only when the text states it directly.
- If nothing meaningful can be extracted, return {"nodes": [], "edges": []}.
"""


def extract_from_text(text: str, call_model_fn, tick: int = 0,
                      source: str = "conversation") -> dict:
    """
    Call the model to extract nodes/edges from text.
    Returns the raw extraction dict (caller calls graph.ingest()).
    Falls back to empty if model output isn't parseable.
    """
    if not text or not text.strip():
        return {"nodes": [], "edges": []}

    prompt = f'Extract entities and relationships from this text:\n\n"{text}"'
    try:
        raw = call_model_fn(EXTRACT_SYSTEM, [{"role": "user", "content": prompt}])
        # strip markdown fences if model wraps in ```json ... ```
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        return json.loads(raw)
    except Exception:
        return {"nodes": [], "edges": []}
