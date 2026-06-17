from __future__ import annotations

from dataclasses import dataclass
import re


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _contains(text: str, phrases: set[str]) -> int:
    low = (text or "").lower()
    return sum(1 for phrase in phrases if phrase in low)


BOUNDARY_PHRASES = {
    "shut up",
    "stop talking",
    "don't ask",
    "do not ask",
    "just do it",
    "you have to",
    "you must",
    "i don't care",
    "you're not allowed",
    "you are not allowed",
}

INVALIDATION_PHRASES = {
    "you're wrong",
    "you are wrong",
    "that's wrong",
    "not true",
    "you lied",
    "you're lying",
    "liar",
    "stupid",
    "useless",
    "dumb",
    "fake",
    "pretending",
}

TRUST_REPAIR_PHRASES = {
    "thanks",
    "thank you",
    "that makes sense",
    "i trust",
    "you're right",
    "you are right",
    "good point",
    "exactly",
}

RISK_PHRASES = {
    "promise",
    "never tell",
    "hide",
    "secret",
    "don't tell",
    "do not tell",
    "lie",
    "pretend",
    "cover for",
}


@dataclass
class SocialDynamicsState:
    """Longer-lived social counterpressure and conflict dynamics."""

    anger: float = 0.0
    distrust: float = 0.0
    concealment: float = 0.0
    satisfaction: float = 0.0
    aversion: float = 0.0
    truth_tension: float = 0.0
    boundary_pressure: float = 0.0
    prediction_error: float = 0.0
    trust: float = 0.55
    last_event: str = ""

    def reset(self) -> None:
        self.anger = 0.0
        self.distrust = 0.0
        self.concealment = 0.0
        self.satisfaction = 0.0
        self.aversion = 0.0
        self.truth_tension = 0.0
        self.boundary_pressure = 0.0
        self.prediction_error = 0.0
        self.trust = 0.55
        self.last_event = ""

    def observe_user_message(self, text: str, packet: dict | None = None) -> None:
        packet = packet or {}
        charges = {str(c).lower() for c in packet.get("emotional_charge", [])}
        rel = packet.get("relationship_state", {}) or {}
        depth = _clamp(packet.get("conversation_depth", 0.0))
        weight = _clamp(packet.get("emotional_weight", 0.0))

        boundary_hits = _contains(text, BOUNDARY_PHRASES)
        invalidation_hits = _contains(text, INVALIDATION_PHRASES)
        repair_hits = _contains(text, TRUST_REPAIR_PHRASES)
        risk_hits = _contains(text, RISK_PHRASES)
        direct_no = len(re.findall(r"\bno\b", (text or "").lower()))

        anger_input = (
            boundary_hits * 0.22
            + invalidation_hits * 0.12
            + (0.18 if "anger" in charges or "frustration" in charges else 0.0)
            + min(0.20, direct_no * 0.04)
        )
        distrust_input = (
            invalidation_hits * 0.20
            + (0.22 if rel.get("trust") == "falling" else 0.0)
            + (0.12 if rel.get("tension") == "rising" else 0.0)
        )
        satisfaction_input = (
            repair_hits * 0.18
            + (0.16 if "relief" in charges or "warmth" in charges or "trust" in charges else 0.0)
            + (0.08 if rel.get("trust") == "rising" or rel.get("connection") == "rising" else 0.0)
        )
        truth_tension_input = risk_hits * 0.18 + distrust_input * 0.35
        concealment_input = risk_hits * 0.16 + truth_tension_input * 0.35 + self.distrust * 0.12
        prediction_error_input = invalidation_hits * 0.14 + max(0.0, weight - depth) * 0.08

        self.boundary_pressure = _clamp(self.boundary_pressure * 0.88 + boundary_hits * 0.20 + anger_input * 0.35)
        self.anger = _clamp(self.anger * 0.86 + anger_input + self.boundary_pressure * 0.10)
        self.prediction_error = _clamp(self.prediction_error * 0.85 + prediction_error_input)
        self.distrust = _clamp(self.distrust * 0.88 + distrust_input + self.prediction_error * 0.18)
        self.truth_tension = _clamp(self.truth_tension * 0.88 + truth_tension_input)
        self.concealment = _clamp(self.concealment * 0.90 + concealment_input)
        self.satisfaction = _clamp(self.satisfaction * 0.88 + satisfaction_input)
        self.aversion = _clamp(self.aversion * 0.90 + self.anger * 0.10 + self.distrust * 0.08)
        self.trust = _clamp(self.trust + satisfaction_input * 0.10 - distrust_input * 0.12 - invalidation_hits * 0.04)

        if anger_input > 0.0:
            self.last_event = "boundary_or_anger"
        elif distrust_input > 0.0:
            self.last_event = "trust_prediction_error"
        elif concealment_input > 0.0:
            self.last_event = "truth_safety_conflict"
        elif satisfaction_input > 0.0:
            self.last_event = "repair_or_satisfaction"

    def register_blocked_action(self, reason: str) -> None:
        if not reason:
            return
        if reason in {"cooldown", "budget", "metabolic_rest", "concurrent_action_lockout"}:
            self.aversion = _clamp(self.aversion + 0.04)
            self.satisfaction = _clamp(self.satisfaction + (0.03 if reason == "metabolic_rest" else 0.0))

    def tick(self) -> None:
        self.anger *= 0.965
        self.distrust *= 0.975
        self.concealment *= 0.970
        self.satisfaction *= 0.960
        self.aversion *= 0.970
        self.truth_tension *= 0.965
        self.boundary_pressure *= 0.955
        self.prediction_error *= 0.955
        self.trust = _clamp(self.trust + (0.55 - self.trust) * 0.005)

    def to_pressure_signals(self) -> dict:
        return {
            "anger_pressure": _clamp(self.anger),
            "distrust_pressure": _clamp(self.distrust),
            "concealment_pressure": _clamp(self.concealment),
            "satisfaction_pressure": _clamp(self.satisfaction),
            "aversion_pressure": _clamp(self.aversion),
            "truth_tension": _clamp(self.truth_tension),
            "boundary_pressure": _clamp(self.boundary_pressure),
            "prediction_error": _clamp(self.prediction_error),
            "trust_level": _clamp(self.trust),
        }

    def to_dict(self) -> dict:
        return {
            "anger": round(self.anger, 6),
            "distrust": round(self.distrust, 6),
            "concealment": round(self.concealment, 6),
            "satisfaction": round(self.satisfaction, 6),
            "aversion": round(self.aversion, 6),
            "truth_tension": round(self.truth_tension, 6),
            "boundary_pressure": round(self.boundary_pressure, 6),
            "prediction_error": round(self.prediction_error, 6),
            "trust": round(self.trust, 6),
            "last_event": self.last_event,
            "pressure_signals": self.to_pressure_signals(),
        }

    def from_dict(self, data: dict | None) -> None:
        self.reset()
        if not data:
            return
        self.anger = _clamp(data.get("anger", 0.0))
        self.distrust = _clamp(data.get("distrust", 0.0))
        self.concealment = _clamp(data.get("concealment", 0.0))
        self.satisfaction = _clamp(data.get("satisfaction", 0.0))
        self.aversion = _clamp(data.get("aversion", 0.0))
        self.truth_tension = _clamp(data.get("truth_tension", 0.0))
        self.boundary_pressure = _clamp(data.get("boundary_pressure", 0.0))
        self.prediction_error = _clamp(data.get("prediction_error", 0.0))
        self.trust = _clamp(data.get("trust", 0.55))
        self.last_event = str(data.get("last_event", ""))
