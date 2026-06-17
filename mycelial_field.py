from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import re


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", "_", (label or "").strip().lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _hash_index(token: str, dims: int) -> int:
    raw = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(raw, "big") % dims


def _vectorize(text: str, dims: int) -> dict[int, float]:
    vec: dict[int, float] = {}
    for token in _tokens(text):
        idx = _hash_index(token, dims)
        vec[idx] = vec.get(idx, 0.0) + 1.0
    mag = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {idx: value / mag for idx, value in vec.items()}


def _cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(idx, 0.0) for idx, value in a.items())


def _blend(a: dict[int, float], b: dict[int, float], alpha: float) -> dict[int, float]:
    out = dict(a)
    for idx, value in b.items():
        out[idx] = out.get(idx, 0.0) * (1.0 - alpha) + value * alpha
    mag = math.sqrt(sum(v * v for v in out.values())) or 1.0
    return {idx: value / mag for idx, value in out.items() if abs(value) > 1e-9}


@dataclass
class FieldNode:
    id: str
    label: str
    type: str = "concept"
    facts: list[str] = field(default_factory=list)
    vector: dict[int, float] = field(default_factory=dict)
    activation: float = 0.0
    stability: float = 0.0
    fatigue: float = 0.0
    first_tick: int = 0
    last_tick: int = 0
    exposures: float = 0.0
    wins: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "facts": list(self.facts),
            "vector": {str(k): round(v, 6) for k, v in self.vector.items()},
            "activation": round(self.activation, 6),
            "stability": round(self.stability, 6),
            "fatigue": round(self.fatigue, 6),
            "first_tick": self.first_tick,
            "last_tick": self.last_tick,
            "exposures": round(self.exposures, 6),
            "wins": round(self.wins, 6),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FieldNode":
        return cls(
            id=data.get("id") or _norm_label(data.get("label", "")),
            label=data.get("label", ""),
            type=data.get("type", "concept"),
            facts=list(data.get("facts", [])),
            vector={int(k): float(v) for k, v in data.get("vector", {}).items()},
            activation=float(data.get("activation", 0.0)),
            stability=float(data.get("stability", 0.0)),
            fatigue=float(data.get("fatigue", 0.0)),
            first_tick=int(data.get("first_tick", 0)),
            last_tick=int(data.get("last_tick", 0)),
            exposures=float(data.get("exposures", 0.0)),
            wins=float(data.get("wins", 0.0)),
        )


class MycelialField:
    """Dependency-free vector/token memory field adapted from TheMycelialCortex."""

    def __init__(
        self,
        dims: int = 128,
        familiar: float = 0.34,
        novel: float = 0.18,
        alpha: float = 0.22,
        budget: int = 96,
        merge_threshold: float = 0.90,
    ) -> None:
        self.dims = int(dims)
        self.familiar = float(familiar)
        self.novel = float(novel)
        self.alpha = float(alpha)
        self.budget = int(budget)
        self.merge_threshold = float(merge_threshold)
        self.nodes: dict[str, FieldNode] = {}
        self.token_stream: list[dict] = []
        self.winner_history: list[str] = []
        self.merge_events: list[dict] = []
        self.token_sequence: int = 0
        self.arrow: float = 0.0
        self.last_demand: float = 0.0
        self.tick_count: int = 0

    def reset(self) -> None:
        self.nodes.clear()
        self.token_stream.clear()
        self.winner_history.clear()
        self.merge_events.clear()
        self.token_sequence = 0
        self.arrow = 0.0
        self.last_demand = 0.0
        self.tick_count = 0

    def ingest_extracted(
        self,
        extracted: dict,
        tick: int,
        source: str,
        pressure_context: dict | None = None,
        atp: float = 1.0,
        learn_enabled: bool = True,
    ) -> None:
        if not extracted:
            return
        energy = self._context_energy(pressure_context)
        for raw in extracted.get("nodes", []):
            label = (raw.get("label") or "").strip()
            if not label:
                continue
            facts = [str(f).strip() for f in raw.get("facts", []) if str(f).strip()]
            text = " ".join([label] + facts)
            confidence = _clamp(raw.get("confidence", 0.7))
            self.perceive(
                text=text,
                label=label,
                ntype=raw.get("type", "concept"),
                facts=facts,
                tick=tick,
                source=source,
                energy=energy * confidence,
                atp=atp,
                learn_enabled=learn_enabled,
            )

        for raw in extracted.get("edges", []):
            source_label = (raw.get("source") or "").strip()
            target_label = (raw.get("target") or "").strip()
            relation = (raw.get("relation") or "related to").strip()
            if source_label and target_label:
                text = f"{source_label} {relation} {target_label}"
                self.perceive(
                    text=text,
                    label=text,
                    ntype="relation",
                    facts=[text],
                    tick=tick,
                    source=source,
                    energy=energy * _clamp(raw.get("confidence", 0.7)) * 0.8,
                    atp=atp,
                    learn_enabled=learn_enabled,
                )

    def perceive(
        self,
        text: str,
        label: str,
        ntype: str = "concept",
        facts: list[str] | None = None,
        tick: int = 0,
        source: str = "input",
        energy: float = 0.35,
        atp: float = 1.0,
        learn_enabled: bool = True,
    ) -> dict:
        vec = _vectorize(text, self.dims)
        if not vec:
            return {"winner": "", "confidence": 0.0, "spawned": False}

        if not self.nodes:
            node = self._spawn(label, ntype, facts or [], vec, tick)
            self._activate(node, energy * 0.65, tick)
            self._emit_token(node, confidence=0.0, tick=tick, source=source, spawned=True)
            return {"winner": node.id, "confidence": 0.0, "spawned": True}

        winner = max(self.nodes.values(), key=lambda node: _cosine(node.vector, vec) - node.fatigue * 0.05)
        confidence = _clamp(_cosine(winner.vector, vec))
        spawned = False

        if learn_enabled and confidence >= self.familiar:
            winner.vector = _blend(winner.vector, vec, self.alpha * _clamp(atp, 0.15, 1.0))
            self._merge_facts(winner, facts or [])
        elif learn_enabled and confidence < self.novel and len(self.nodes) < self.budget and atp > 0.25:
            winner = self._spawn(label, ntype, facts or [], vec, tick)
            confidence = 0.0
            spawned = True

        self._activate(winner, energy * (0.5 + confidence * 0.5), tick)
        if learn_enabled:
            self._merge_similar_nodes(tick)
            if winner.id not in self.nodes and self.nodes:
                winner = max(self.nodes.values(), key=lambda node: _cosine(node.vector, vec))
        self._emit_token(winner, confidence=confidence, tick=tick, source=source, spawned=spawned)
        self.last_demand = _clamp(0.04 + energy * 0.18 + (0.10 if spawned else 0.0))
        return {"winner": winner.id, "confidence": confidence, "spawned": spawned}

    def tick(self, pressure_context: dict | None, tick: int, atp: float = 1.0) -> None:
        self.tick_count = tick
        energy = self._context_energy(pressure_context)
        for node in self.nodes.values():
            previous = node.activation
            node.activation = max(0.0, node.activation * (0.965 - node.fatigue * 0.03))
            node.fatigue = _clamp(node.fatigue * 0.94 + max(0.0, previous - node.activation) * 0.02)
            if node.activation > 0.08:
                node.stability = _clamp(node.stability * 0.982 + node.activation * energy * atp * 0.025)
            else:
                node.stability *= 0.998
        if atp > 0.18:
            self._merge_similar_nodes(tick)
        self._update_arrow()
        self.token_stream = self.token_stream[-80:]
        self.merge_events = self.merge_events[-40:]

    def stable_nodes(self, max_nodes: int | None = None) -> list[FieldNode]:
        ranked = sorted(
            self.nodes.values(),
            key=lambda node: (node.stability * 0.55 + node.activation * 0.25 + min(node.exposures / 8.0, 1.0) * 0.20) - node.fatigue * 0.15,
            reverse=True,
        )
        stable = [
            node for node in ranked
            if node.stability >= 0.12 and node.exposures > 1.0 and node.activation > 0.03
        ]
        return stable[:max_nodes] if max_nodes is not None else stable

    def context_text(self, max_nodes: int = 6) -> str:
        nodes = self.stable_nodes(max_nodes=max_nodes)
        if not nodes:
            return ""
        lines = ["Mycelial field context:"]
        for node in nodes:
            fact = "; ".join(node.facts[:2]) if node.facts else "field-stabilized pattern"
            lines.append(
                f"  [{node.type}] {node.label} "
                f"activation={node.activation:.2f} stability={node.stability:.2f}: {fact}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "dims": self.dims,
            "familiar": self.familiar,
            "novel": self.novel,
            "alpha": self.alpha,
            "budget": self.budget,
            "merge_threshold": self.merge_threshold,
            "tick_count": self.tick_count,
            "arrow": round(self.arrow, 6),
            "last_demand": round(self.last_demand, 6),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "stable_count": len(self.stable_nodes()),
            "token_stream": list(self.token_stream[-24:]),
            "winner_history": list(self.winner_history[-24:]),
            "merge_events": list(self.merge_events[-12:]),
            "token_sequence": self.token_sequence,
            "context": self.context_text(),
        }

    def from_dict(self, data: dict | None) -> None:
        self.reset()
        if not data:
            return
        self.dims = int(data.get("dims", self.dims))
        self.familiar = float(data.get("familiar", self.familiar))
        self.novel = float(data.get("novel", self.novel))
        self.alpha = float(data.get("alpha", self.alpha))
        self.budget = int(data.get("budget", self.budget))
        self.merge_threshold = float(data.get("merge_threshold", self.merge_threshold))
        self.tick_count = int(data.get("tick_count", 0))
        self.arrow = float(data.get("arrow", 0.0))
        self.last_demand = float(data.get("last_demand", 0.0))
        for raw in data.get("nodes", []):
            node = FieldNode.from_dict(raw)
            if node.id:
                self.nodes[node.id] = node
        self.token_stream = list(data.get("token_stream", []))[-80:]
        self.winner_history = list(data.get("winner_history", []))[-80:]
        self.merge_events = list(data.get("merge_events", []))[-40:]
        self.token_sequence = int(data.get("token_sequence", len(self.token_stream)))

    def _spawn(self, label: str, ntype: str, facts: list[str], vec: dict[int, float], tick: int) -> FieldNode:
        base = _norm_label(label) or f"node_{len(self.nodes) + 1}"
        nid = base
        suffix = 2
        while nid in self.nodes:
            nid = f"{base}_{suffix}"
            suffix += 1
        node = FieldNode(
            id=nid,
            label=label,
            type=ntype or "concept",
            facts=[],
            vector=dict(vec),
            first_tick=tick,
            last_tick=tick,
        )
        self._merge_facts(node, facts)
        self.nodes[nid] = node
        return node

    def _merge_facts(self, node: FieldNode, facts: list[str]) -> None:
        for fact in facts:
            if fact and fact not in node.facts:
                node.facts.append(fact)
        node.facts = node.facts[:8]

    def _merge_similar_nodes(self, tick: int) -> None:
        if len(self.nodes) < 2:
            return
        ids = sorted(self.nodes)
        best_pair = None
        best_similarity = self.merge_threshold
        for i, left_id in enumerate(ids):
            left = self.nodes.get(left_id)
            if not left:
                continue
            for right_id in ids[i + 1:]:
                right = self.nodes.get(right_id)
                if not right:
                    continue
                similarity = _cosine(left.vector, right.vector)
                if similarity >= best_similarity:
                    best_pair = (left_id, right_id)
                    best_similarity = similarity
        if not best_pair:
            return
        left = self.nodes[best_pair[0]]
        right = self.nodes[best_pair[1]]
        keep, absorb = (left, right)
        if (right.stability + right.exposures) > (left.stability + left.exposures):
            keep, absorb = right, left

        total = max(keep.exposures + absorb.exposures, 1e-9)
        alpha = absorb.exposures / total
        keep.vector = _blend(keep.vector, absorb.vector, alpha)
        keep.activation = _clamp(max(keep.activation, absorb.activation) + min(keep.activation, absorb.activation) * 0.25)
        keep.stability = _clamp(max(keep.stability, absorb.stability) + min(keep.stability, absorb.stability) * 0.15)
        keep.fatigue = _clamp((keep.fatigue + absorb.fatigue) * 0.5)
        keep.exposures += absorb.exposures
        keep.wins += absorb.wins
        keep.last_tick = max(keep.last_tick, absorb.last_tick, tick)
        keep.first_tick = min(keep.first_tick, absorb.first_tick)
        self._merge_facts(keep, absorb.facts)
        if keep.type == "concept" and absorb.type != "concept":
            keep.type = absorb.type

        old_id = absorb.id
        del self.nodes[old_id]
        self.winner_history = [keep.id if nid == old_id else nid for nid in self.winner_history]
        for token in self.token_stream:
            if token.get("node") == old_id:
                token["node"] = keep.id
                token["merged_from"] = old_id
        self.merge_events.append({
            "tick": tick,
            "kept": keep.id,
            "absorbed": old_id,
            "similarity": round(best_similarity, 6),
        })

    def _activate(self, node: FieldNode, energy: float, tick: int) -> None:
        energy = _clamp(energy)
        node.activation = _clamp(node.activation + energy * (1.0 - node.activation * 0.35))
        node.exposures += energy
        node.wins += 1.0
        node.last_tick = tick
        self.winner_history.append(node.id)
        self.winner_history = self.winner_history[-80:]

    def _emit_token(self, node: FieldNode, confidence: float, tick: int, source: str, spawned: bool) -> None:
        sparse = sorted(node.vector.items(), key=lambda item: abs(item[1]), reverse=True)[:8]
        previous = self.winner_history[-2] if len(self.winner_history) >= 2 else ""
        chi = 0
        if previous and previous < node.id:
            chi = 1
        elif previous and previous > node.id:
            chi = -1
        self.token_sequence += 1
        self.token_stream.append({
            "seq": self.token_sequence,
            "tick": tick,
            "node": node.id,
            "prev_node": previous,
            "label": node.label,
            "chi": chi,
            "confidence": round(confidence, 6),
            "spawned": spawned,
            "source": source,
            "payload": [[idx, round(value, 6)] for idx, value in sparse],
        })

    def _update_arrow(self) -> None:
        history = self.winner_history[-24:]
        if len(history) < 3:
            self.arrow *= 0.96
            return
        forward = 0.0
        reverse = 0.0
        for prev, cur in zip(history, history[1:]):
            if prev < cur:
                forward += 1.0
            elif prev > cur:
                reverse += 1.0
        total = forward + reverse
        self.arrow = 0.0 if total <= 0 else (forward - reverse) / total

    def _context_energy(self, pressure_context: dict | None) -> float:
        if not pressure_context:
            return 0.35
        values = [abs(float(v or 0.0)) for v in pressure_context.values()]
        return _clamp(sum(values) / max(1, len(values)), 0.12, 1.0)
