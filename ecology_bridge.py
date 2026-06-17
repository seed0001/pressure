from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


@dataclass
class EcologyState:
    """Pressure-facing adapter for computational-life metrics."""

    entropy: float = 0.0
    previous_entropy: float | None = None
    unique_ratio: float = 0.0
    territorial_dominance: float = 0.0
    lineage_flux: float = 0.0
    entropy_shift: float = 0.0
    stagnation: float = 0.0
    novelty: float = 0.0
    last_epoch: int = 0
    samples: int = 0

    def reset(self) -> None:
        self.entropy = 0.0
        self.previous_entropy = None
        self.unique_ratio = 0.0
        self.territorial_dominance = 0.0
        self.lineage_flux = 0.0
        self.entropy_shift = 0.0
        self.stagnation = 0.0
        self.novelty = 0.0
        self.last_epoch = 0
        self.samples = 0

    def ingest_metrics(self, metrics: dict | None) -> None:
        if not metrics:
            self.decay()
            return

        entropy = _clamp(metrics.get("entropy", metrics.get("high_order_entropy", self.entropy)))
        unique_ratio = metrics.get("unique_ratio")
        if unique_ratio is None:
            unique_count = float(metrics.get("unique_count", metrics.get("unique_program_count", 0.0)) or 0.0)
            population = float(metrics.get("population", metrics.get("population_size", 0.0)) or 0.0)
            unique_ratio = unique_count / population if population > 0 else self.unique_ratio

        dominance = metrics.get("territorial_dominance")
        if dominance is None:
            dominance = 1.0 - float(unique_ratio or 0.0)

        entropy_shift = 0.0 if self.previous_entropy is None else entropy - self.previous_entropy
        self.entropy_shift = entropy_shift

        self.previous_entropy = entropy
        self.entropy = entropy
        self.unique_ratio = _clamp(unique_ratio or 0.0)
        new_dominance = _clamp(dominance)
        self.lineage_flux = _clamp(abs(new_dominance - self.territorial_dominance) * 3.0)
        self.territorial_dominance = new_dominance
        self.novelty = _clamp(abs(entropy_shift) * 2.5 + self.lineage_flux * 0.5 + self.unique_ratio * 0.2)
        if abs(entropy_shift) < 0.01 and self.lineage_flux < 0.03:
            self.stagnation = _clamp(self.stagnation + 0.08)
        else:
            self.stagnation = _clamp(self.stagnation * 0.75)
        self.last_epoch = int(metrics.get("epoch", self.last_epoch) or 0)
        self.samples += 1

    def decay(self) -> None:
        self.lineage_flux *= 0.92
        self.entropy_shift *= 0.90
        self.novelty *= 0.90
        self.stagnation = _clamp(self.stagnation * 0.985)

    def to_pressure_signals(self) -> dict:
        return {
            "ecology_entropy_shift": _clamp(abs(self.entropy_shift) * 2.5),
            "ecology_diversity": self.unique_ratio,
            "ecology_lineage_flux": self.lineage_flux,
            "ecology_stagnation": self.stagnation,
            "ecology_novelty": self.novelty,
        }

    def to_dict(self) -> dict:
        return {
            "entropy": round(self.entropy, 6),
            "previous_entropy": None if self.previous_entropy is None else round(self.previous_entropy, 6),
            "unique_ratio": round(self.unique_ratio, 6),
            "territorial_dominance": round(self.territorial_dominance, 6),
            "lineage_flux": round(self.lineage_flux, 6),
            "entropy_shift": round(self.entropy_shift, 6),
            "stagnation": round(self.stagnation, 6),
            "novelty": round(self.novelty, 6),
            "last_epoch": self.last_epoch,
            "samples": self.samples,
            "pressure_signals": self.to_pressure_signals(),
        }

    def from_dict(self, data: dict | None) -> None:
        self.reset()
        if not data:
            return
        self.entropy = _clamp(data.get("entropy", 0.0))
        prev = data.get("previous_entropy")
        self.previous_entropy = None if prev is None else _clamp(prev)
        self.unique_ratio = _clamp(data.get("unique_ratio", 0.0))
        self.territorial_dominance = _clamp(data.get("territorial_dominance", 0.0))
        self.lineage_flux = _clamp(data.get("lineage_flux", 0.0))
        self.entropy_shift = float(data.get("entropy_shift", 0.0) or 0.0)
        self.stagnation = _clamp(data.get("stagnation", 0.0))
        self.novelty = _clamp(data.get("novelty", 0.0))
        self.last_epoch = int(data.get("last_epoch", 0) or 0)
        self.samples = int(data.get("samples", 0) or 0)
