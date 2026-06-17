import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import metabolism
import mycelial_field
import ecology_bridge
import pressure_engine as pe


EXTRACTED = {
    "nodes": [
        {
            "label": "Living conversational container",
            "type": "concept",
            "facts": ["The entity combines pressure, field memory, and ecology"],
            "confidence": 0.9,
        },
        {
            "label": "Field memory",
            "type": "concept",
            "facts": ["Recall grows through resonance and consolidation"],
            "confidence": 0.85,
        },
    ],
    "edges": [
        {
            "source": "Living conversational container",
            "target": "Field memory",
            "relation": "uses",
            "confidence": 0.8,
        }
    ],
}


def test_mycelial_field_stabilizes_after_reactivation():
    field = mycelial_field.MycelialField()
    pressure = {"Curiosity": 0.8, "Learn": 0.7}

    field.ingest_extracted(EXTRACTED, tick=1, source="test", pressure_context=pressure, atp=1.0)
    assert field.nodes, "first exposure should enter the field"
    assert not field.stable_nodes(), "first exposure should not be stable field memory"

    for tick in range(2, 45):
        field.ingest_extracted(EXTRACTED, tick=tick, source="test", pressure_context=pressure, atp=1.0)
        field.tick(pressure, tick, atp=1.0)

    assert field.stable_nodes(), "repeated resonance should stabilize field memory"
    assert field.token_stream, "field should emit sparse tokens"
    assert field.context_text(), "stable field structures should expose prompt context"
    assert "seq" in field.token_stream[-1], "tokens should preserve ordered sequence"
    assert "chi" in field.token_stream[-1], "tokens should carry chirality"


def test_mycelial_field_merges_redundant_fragments():
    field = mycelial_field.MycelialField(merge_threshold=0.9)
    pressure = {"Curiosity": 0.8, "Learn": 0.7}
    vec = mycelial_field._vectorize("maps navigation route memory", field.dims)
    left = field._spawn("maps navigation", "concept", ["maps navigation"], vec, tick=1)
    right = field._spawn("navigation maps", "concept", ["navigation maps"], vec, tick=1)
    field._activate(left, 0.8, tick=1)
    field._activate(right, 0.6, tick=1)
    field.tick(pressure, tick=2, atp=1.0)
    assert len(field.nodes) == 1, "near-identical fragments should merge instead of filling the budget"
    assert field.merge_events, "field should record merge-on-consolidate events"


def test_metabolism_gates_growth_when_exhausted():
    state = metabolism.MetabolismState(atp=0.2, fatigue=0.9)
    field = mycelial_field.MycelialField()
    pressure = {"Curiosity": 0.8}

    field.ingest_extracted(EXTRACTED, tick=1, source="test", pressure_context=pressure, atp=1.0)
    before = len(field.nodes)
    novel = {
        "nodes": [
            {
                "label": "Completely new signal",
                "type": "concept",
                "facts": ["A different pressure source appears"],
                "confidence": 0.9,
            }
        ],
        "edges": [],
    }
    field.ingest_extracted(
        novel,
        tick=2,
        source="test",
        pressure_context=pressure,
        atp=state.recall_gain(),
        learn_enabled=state.can_grow(),
    )
    assert len(field.nodes) == before, "exhausted metabolism should gate new growth"


def test_pressure_engine_routes_into_living_organs():
    pe.reset()
    pressure = {"Curiosity": 0.8, "Learn": 0.7}
    pe._ingest_living_memory(EXTRACTED, tick=1, source="test", pressure_context=pressure)

    assert pe.get_memory_field()["nodes"], "symbolic pressure memory should receive extracted content"
    assert pe.get_mycelial_field()["nodes"], "mycelial field should receive extracted content"
    assert pe.get_metabolism()["total_spent"] > 0.0, "memory ingestion should cost ATP"

    for tick in range(2, 45):
        pe._ingest_living_memory(EXTRACTED, tick=tick, source="test", pressure_context=pressure)
        pe.charge_only_tick(pressure)

    assert pe.get_mycelial_field()["stable_count"] > 0, "engine ticks should stabilize mycelial memory"
    assert "Metabolic state" in pe._living_context_text(), "prompt context should include metabolism"


def test_ecology_metrics_feed_pressure_signals():
    eco = ecology_bridge.EcologyState()
    eco.ingest_metrics({"epoch": 1, "high_order_entropy": 0.8, "unique_count": 90, "population": 100})
    eco.ingest_metrics({"epoch": 2, "high_order_entropy": 0.55, "unique_count": 30, "population": 100})
    signals = eco.to_pressure_signals()
    assert signals["ecology_entropy_shift"] > 0.0, "entropy movement should feed reflective pressure"
    assert signals["ecology_lineage_flux"] > 0.0, "dominance movement should feed curiosity"


def test_metabolic_rest_blocks_research():
    pe.reset()
    pe.metabolism.atp = 0.1
    pe.metabolism.fatigue = 0.95
    assert pe._metabolic_block_reason("research") == "metabolic_rest"
    assert pe._metabolic_block_reason("reach_out") == ""


def run():
    test_mycelial_field_stabilizes_after_reactivation()
    test_mycelial_field_merges_redundant_fragments()
    test_metabolism_gates_growth_when_exhausted()
    test_pressure_engine_routes_into_living_organs()
    test_ecology_metrics_feed_pressure_signals()
    test_metabolic_rest_blocks_research()


if __name__ == "__main__":
    run()
    print("living container OK")
