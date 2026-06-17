from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


@dataclass
class MetabolismState:
    """Small shared energy state for learning, recall, and expression."""

    atp: float = 1.0
    fatigue: float = 0.0
    rest_drive: float = 0.0
    last_demand: float = 0.0
    total_spent: float = 0.0

    def reset(self) -> None:
        self.atp = 1.0
        self.fatigue = 0.0
        self.rest_drive = 0.0
        self.last_demand = 0.0
        self.total_spent = 0.0

    def can_grow(self) -> bool:
        return self.atp > 0.25 and self.fatigue < 0.85

    def recall_gain(self) -> float:
        return _clamp(0.35 + self.atp * 0.75 - self.fatigue * 0.25, 0.15, 1.0)

    def spend(self, amount: float) -> None:
        amount = _clamp(amount, 0.0, 1.0)
        self.last_demand = amount
        self.total_spent += amount
        self.atp = _clamp(self.atp - amount * 0.18)
        self.fatigue = _clamp(self.fatigue + amount * 0.12)

    def tick(self, pressure_context: dict | None = None) -> None:
        pressure_load = 0.0
        if pressure_context:
            values = [abs(float(v or 0.0)) for v in pressure_context.values()]
            pressure_load = _clamp(sum(values) / max(1, len(values)))

        # High pressure load should actively drain ATP and accumulate fatigue.
        recovery = 0.02 + max(0.0, 0.35 - pressure_load) * 0.03
        drain = pressure_load * 0.06
        self.atp = _clamp(self.atp + recovery - drain)
        # Fatigue builds under sustained load, but rests off when load is low.
        fatigue_accumulation = max(0.0, pressure_load - 0.3) * 0.05
        self.fatigue = _clamp(self.fatigue * 0.96 + fatigue_accumulation)
        self.rest_drive = _clamp((1.0 - self.atp) * 0.65 + self.fatigue * 0.55)
        self.last_demand *= 0.85

    def to_dict(self) -> dict:
        return {
            "atp": round(self.atp, 6),
            "fatigue": round(self.fatigue, 6),
            "rest_drive": round(self.rest_drive, 6),
            "last_demand": round(self.last_demand, 6),
            "total_spent": round(self.total_spent, 6),
            "can_grow": self.can_grow(),
            "recall_gain": round(self.recall_gain(), 6),
        }

    def from_dict(self, data: dict | None) -> None:
        self.reset()
        if not data:
            return
        self.atp = _clamp(data.get("atp", 1.0))
        self.fatigue = _clamp(data.get("fatigue", 0.0))
        self.rest_drive = _clamp(data.get("rest_drive", 0.0))
        self.last_demand = _clamp(data.get("last_demand", 0.0))
        self.total_spent = max(0.0, float(data.get("total_spent", 0.0) or 0.0))
