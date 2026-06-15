"""
Pressure memory field.

This module is deliberately mechanical. It does not decide that a category of
information is special, and it does not permanently admit a first encounter as
memory. Extracted concepts enter a volatile pressure graph. Repeated activation,
connection flow, low volatility, and participation in the engine gradually make
some structures persistent enough to project into the compatibility knowledge
graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re


def normalize(label: str) -> str:
    return re.sub(r"\s+", "_", (label or "").strip().lower())


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class MemoryNode:
    id: str
    label: str
    type: str = "concept"
    facts: list[str] = field(default_factory=list)
    pressure: float = 0.0
    stability: float = 0.0
    volatility: float = 0.0
    persistence: float = 0.0
    first_tick: int = 0
    last_tick: int = 0
    activation_count: float = 0.0
    activation_history: list[dict] = field(default_factory=list)
    pathways: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "facts": list(self.facts),
            "pressure": round(self.pressure, 6),
            "stability": round(self.stability, 6),
            "volatility": round(self.volatility, 6),
            "persistence": round(self.persistence, 6),
            "first_tick": self.first_tick,
            "last_tick": self.last_tick,
            "activation_count": round(self.activation_count, 6),
            "activation_history": list(self.activation_history[-12:]),
            "pathways": {k: round(v, 6) for k, v in self.pathways.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryNode":
        return cls(
            id=data.get("id") or normalize(data.get("label", "")),
            label=data.get("label", ""),
            type=data.get("type", "concept"),
            facts=list(data.get("facts", [])),
            pressure=float(data.get("pressure", 0.0)),
            stability=float(data.get("stability", 0.0)),
            volatility=float(data.get("volatility", 0.0)),
            persistence=float(data.get("persistence", 0.0)),
            first_tick=int(data.get("first_tick", 0)),
            last_tick=int(data.get("last_tick", 0)),
            activation_count=float(data.get("activation_count", 0.0)),
            activation_history=list(data.get("activation_history", []))[-12:],
            pathways={str(k): float(v) for k, v in data.get("pathways", {}).items()},
        )


@dataclass
class MemoryEdge:
    source_id: str
    target_id: str
    relation: str = "related to"
    weight: float = 0.0
    pressure: float = 0.0
    first_tick: int = 0
    last_tick: int = 0
    activation_count: float = 0.0

    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.relation)

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "relation": self.relation,
            "weight": round(self.weight, 6),
            "pressure": round(self.pressure, 6),
            "first_tick": self.first_tick,
            "last_tick": self.last_tick,
            "activation_count": round(self.activation_count, 6),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEdge":
        return cls(
            source_id=data.get("source", ""),
            target_id=data.get("target", ""),
            relation=data.get("relation", "related to"),
            weight=float(data.get("weight", 0.0)),
            pressure=float(data.get("pressure", 0.0)),
            first_tick=int(data.get("first_tick", 0)),
            last_tick=int(data.get("last_tick", 0)),
            activation_count=float(data.get("activation_count", 0.0)),
        )


class PressureMemoryField:
    def __init__(self) -> None:
        self.nodes: dict[str, MemoryNode] = {}
        self.edges: dict[tuple[str, str, str], MemoryEdge] = {}
        self.recent_activation_paths: list[dict] = []
        self.tick_count: int = 0

    def reset(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.recent_activation_paths.clear()
        self.tick_count = 0

    def to_dict(self) -> dict:
        return {
            "tick_count": self.tick_count,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges.values()],
            "recent_activation_paths": list(self.recent_activation_paths[-24:]),
        }

    def from_dict(self, data: dict | None) -> None:
        self.reset()
        if not data:
            return
        self.tick_count = int(data.get("tick_count", 0))
        for raw in data.get("nodes", []):
            node = MemoryNode.from_dict(raw)
            if node.id:
                self.nodes[node.id] = node
        for raw in data.get("edges", []):
            edge = MemoryEdge.from_dict(raw)
            if edge.source_id in self.nodes and edge.target_id in self.nodes:
                self.edges[edge.key()] = edge
        self.recent_activation_paths = list(data.get("recent_activation_paths", []))[-24:]

    def ingest_extracted(self, extracted: dict, tick: int, source: str, pressure_context: dict | None = None) -> None:
        if not extracted:
            return
        energy = self._context_energy(pressure_context)
        touched: list[str] = []
        for raw in extracted.get("nodes", []):
            label = (raw.get("label") or "").strip()
            if not label:
                continue
            node = self._ensure_node(
                label=label,
                ntype=raw.get("type", "concept"),
                facts=raw.get("facts", []),
                tick=tick,
            )
            confidence = _clamp(float(raw.get("confidence", 0.7)))
            self._activate_node(node.id, energy * confidence, tick, f"input:{source}")
            touched.append(node.id)

        for raw in extracted.get("edges", []):
            src = (raw.get("source") or "").strip()
            tgt = (raw.get("target") or "").strip()
            if not src or not tgt:
                continue
            src_node = self._ensure_node(src, tick=tick)
            tgt_node = self._ensure_node(tgt, tick=tick)
            relation = (raw.get("relation") or "related to").strip()
            confidence = _clamp(float(raw.get("confidence", 0.7)))
            self._strengthen_edge(src_node.id, tgt_node.id, relation, energy * confidence, tick)
            self._activate_node(src_node.id, energy * confidence * 0.6, tick, f"edge:{source}")
            self._activate_node(tgt_node.id, energy * confidence * 0.6, tick, f"edge:{source}")
            touched.extend([src_node.id, tgt_node.id])

        if len(touched) > 1:
            ordered = sorted(set(touched))
            for i, src_id in enumerate(ordered):
                for tgt_id in ordered[i + 1:]:
                    self._strengthen_edge(src_id, tgt_id, "co-activated with", energy * 0.35, tick)

    def tick(self, pressure_context: dict | None, tick: int) -> None:
        self.tick_count = tick
        if not self.nodes:
            return

        selected = self._select_nodes_by_pressure(tick)
        path = []
        for nid in selected:
            if nid not in self.nodes:
                continue
            path.append(nid)
            node = self.nodes[nid]
            engine_alignment = self._context_energy(pressure_context)
            connection_factor = self._connection_factor(nid)
            activation = node.pressure * (0.35 + engine_alignment * 0.35 + connection_factor * 0.30)
            self._activate_node(nid, activation, tick, "internal")
            self._propagate_from(nid, activation, tick, path)

        self._apply_decay_and_stabilize(tick)
        if path:
            self.recent_activation_paths.append({"tick": tick, "path": path[-12:]})
            self.recent_activation_paths = self.recent_activation_paths[-24:]

    def context_text(self, max_nodes: int = 8) -> str:
        projected = self.projectable_nodes(max_nodes=max_nodes)
        if not projected:
            return ""
        lines = ["Pressure-stabilized memory context:"]
        for node in projected:
            fact_str = "; ".join(node.facts[:3]) if node.facts else "no stable facts yet"
            lines.append(
                f"  [{node.type}] {node.label} "
                f"pressure={node.pressure:.2f} stability={node.stability:.2f}: {fact_str}"
            )
            for edge in self._neighbor_edges(node.id)[:3]:
                other_id = edge.target_id if edge.source_id == node.id else edge.source_id
                other = self.nodes.get(other_id)
                if other:
                    lines.append(f"    -- {edge.relation} ({edge.weight:.2f}) -- {other.label}")
        return "\n".join(lines)

    def projectable_nodes(self, max_nodes: int | None = None) -> list[MemoryNode]:
        if not self.nodes:
            return []
        scores = [self._persistence_score(node) for node in self.nodes.values()]
        field_mean = sum(scores) / len(scores)
        field_variance = sum((score - field_mean) ** 2 for score in scores) / len(scores)
        field_spread = math.sqrt(field_variance)
        dynamic_frontier = field_mean + field_spread
        ranked = sorted(
            self.nodes.values(),
            key=lambda node: self._persistence_score(node),
            reverse=True,
        )
        stable = [
            node for node in ranked
            if self._persistence_score(node) >= dynamic_frontier
            and node.stability >= node.volatility
            and self._connection_factor(node.id) > 0.0
        ]
        if not stable and len(self.nodes) == 1:
            node = ranked[0]
            if node.stability >= node.volatility and node.activation_count > 1.0:
                stable = [node]
        return stable[:max_nodes] if max_nodes is not None else stable

    def project_to_knowledge_graph(self, graph, max_nodes: int | None = None) -> None:
        graph.reset()
        stable_ids = {node.id for node in self.projectable_nodes(max_nodes=max_nodes)}
        for node in sorted((self.nodes[nid] for nid in stable_ids), key=lambda n: -self._persistence_score(n)):
            graph.add_node(
                label=node.label,
                ntype=node.type,
                facts=list(node.facts),
                confidence=_clamp(self._persistence_score(node)),
                tick=node.last_tick,
                source="pressure_memory",
            )
        for edge in sorted(self.edges.values(), key=lambda e: -(e.weight + e.pressure)):
            if edge.source_id in stable_ids and edge.target_id in stable_ids:
                src = self.nodes.get(edge.source_id)
                tgt = self.nodes.get(edge.target_id)
                if src and tgt:
                    graph.add_edge(
                        src.label,
                        tgt.label,
                        edge.relation,
                        weight=_clamp(edge.weight),
                        confidence=_clamp((edge.weight + edge.pressure) / 2.0),
                        tick=edge.last_tick,
                        source="pressure_memory",
                    )

    def _ensure_node(self, label: str, ntype: str = "concept", facts: list | None = None, tick: int = 0) -> MemoryNode:
        nid = normalize(label)
        if nid not in self.nodes:
            self.nodes[nid] = MemoryNode(id=nid, label=label, type=ntype or "concept", first_tick=tick, last_tick=tick)
        node = self.nodes[nid]
        if ntype and node.type == "concept":
            node.type = ntype
        for fact in facts or []:
            clean = str(fact).strip()
            if clean and clean not in node.facts:
                node.facts.append(clean)
        node.last_tick = max(node.last_tick, tick)
        return node

    def _strengthen_edge(self, src_id: str, tgt_id: str, relation: str, energy: float, tick: int) -> None:
        if src_id == tgt_id:
            return
        key = (src_id, tgt_id, relation)
        if key not in self.edges:
            self.edges[key] = MemoryEdge(src_id, tgt_id, relation, first_tick=tick, last_tick=tick)
        edge = self.edges[key]
        delta = _clamp(energy) * (1.0 - edge.weight * 0.5)
        edge.weight = _clamp(edge.weight + delta)
        edge.pressure = _clamp(edge.pressure + delta * 0.8)
        edge.activation_count += delta
        edge.last_tick = tick

    def _activate_node(self, nid: str, energy: float, tick: int, pathway: str) -> None:
        node = self.nodes.get(nid)
        if not node:
            return
        energy = _clamp(energy)
        previous = node.pressure
        node.pressure = _clamp(node.pressure + energy * (1.0 - node.pressure * 0.45))
        node.volatility = (node.volatility * 0.82) + (abs(node.pressure - previous) * 0.18)
        node.activation_count += energy
        node.last_tick = tick
        node.pathways[pathway] = node.pathways.get(pathway, 0.0) + energy
        node.activation_history.append({"tick": tick, "energy": round(energy, 4), "pathway": pathway})
        node.activation_history = node.activation_history[-12:]

    def _propagate_from(self, nid: str, activation: float, tick: int, path: list[str]) -> None:
        for edge in self._neighbor_edges(nid):
            other_id = edge.target_id if edge.source_id == nid else edge.source_id
            if other_id not in self.nodes:
                continue
            flowed = activation * edge.weight * (0.22 + edge.pressure * 0.18)
            if flowed <= 0.0:
                continue
            edge.pressure = _clamp(edge.pressure + flowed * 0.3)
            edge.activation_count += flowed
            edge.last_tick = tick
            self._activate_node(other_id, flowed, tick, f"relational:{nid}")
            path.append(other_id)

    def _apply_decay_and_stabilize(self, tick: int) -> None:
        for node in self.nodes.values():
            connectedness = self._connection_factor(node.id)
            idle_span = max(0, tick - node.last_tick)
            decay = (0.018 + idle_span * 0.002) * (1.0 - connectedness * 0.55)
            previous = node.pressure
            node.pressure = max(0.0, node.pressure * (1.0 - decay))
            node.volatility = (node.volatility * 0.94) + (abs(previous - node.pressure) * 0.06)
            node.stability = _clamp((node.stability * 0.96) + (node.pressure * (1.0 - node.volatility) * 0.04))
            node.persistence = max(0.0, (node.persistence * 0.992) + self._persistence_score(node) * 0.008)

        for edge in self.edges.values():
            edge.pressure = max(0.0, edge.pressure * (1.0 - 0.025 * (1.0 - edge.weight * 0.4)))
            edge.weight = max(0.0, edge.weight * 0.998)

    def _select_nodes_by_pressure(self, tick: int) -> list[str]:
        total = sum(max(0.0, node.pressure) for node in self.nodes.values())
        if total <= 0.0:
            return []
        ranked = sorted(self.nodes.values(), key=lambda n: n.id)
        count_float = math.sqrt(len(ranked))
        count = max(1, min(len(ranked), int(math.ceil(count_float))))
        selected: list[str] = []
        cursor = ((tick * 0.6180339887498949) % 1.0) * total
        for _ in range(count):
            running = 0.0
            for node in ranked:
                running += max(0.0, node.pressure)
                if running >= cursor:
                    if node.id not in selected:
                        selected.append(node.id)
                    break
            cursor = (cursor + (total / max(1, count))) % total
        return selected

    def _neighbor_edges(self, nid: str) -> list[MemoryEdge]:
        edges = [edge for edge in self.edges.values() if edge.source_id == nid or edge.target_id == nid]
        return sorted(edges, key=lambda edge: edge.weight + edge.pressure, reverse=True)

    def _connection_factor(self, nid: str) -> float:
        edges = self._neighbor_edges(nid)
        if not edges:
            return 0.0
        total = sum(edge.weight + edge.pressure for edge in edges)
        return _clamp(total / (len(edges) + 1.0))

    def _pathway_diversity(self, node: MemoryNode) -> float:
        if not node.pathways:
            return 0.0
        total = sum(max(0.0, value) for value in node.pathways.values())
        if total <= 0.0:
            return 0.0
        entropy = 0.0
        for value in node.pathways.values():
            p = max(0.0, value) / total
            if p > 0.0:
                entropy -= p * math.log(p)
        return _clamp(entropy / math.log(len(node.pathways) + 1.0))

    def _persistence_score(self, node: MemoryNode) -> float:
        return _clamp(
            ((node.pressure + node.stability + node.persistence) / 3.0)
            * (1.0 - node.volatility)
            * (0.55 + self._connection_factor(node.id) * 0.25 + self._pathway_diversity(node) * 0.20)
        )

    def _context_energy(self, pressure_context: dict | None) -> float:
        if not pressure_context:
            return 0.35
        values = [abs(float(v or 0.0)) for v in pressure_context.values()]
        if not values:
            return 0.35
        return _clamp(sum(values) / len(values))
