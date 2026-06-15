import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pressure_memory as pm
import knowledge_graph as kg


def run():
    field = pm.PressureMemoryField()
    extracted = {
        "nodes": [
            {
                "label": "User likes maps",
                "type": "concept",
                "facts": ["User likes maps"],
                "confidence": 0.9,
            },
            {
                "label": "Navigation projects",
                "type": "concept",
                "facts": ["Navigation projects matter"],
                "confidence": 0.8,
            },
        ],
        "edges": [
            {
                "source": "User likes maps",
                "target": "Navigation projects",
                "relation": "connects to",
                "confidence": 0.8,
            }
        ],
    }
    pressure = {"Learn": 0.7, "Curiosity": 0.6}

    field.ingest_extracted(extracted, tick=1, source="conversation", pressure_context=pressure)
    assert len(field.projectable_nodes()) == 0, "first encounter must not become persistent"

    for tick in range(2, 30):
        field.tick(pressure, tick)

    stable = field.projectable_nodes()
    assert stable, "repeated internal circulation should stabilize at least one structure"
    assert field.recent_activation_paths, "field should expose recent activation paths"

    graph = kg.KnowledgeGraph()
    field.project_to_knowledge_graph(graph)
    assert graph.nodes, "stable field structures should project to compatibility graph"
    assert field.context_text(), "pressure-first retrieval should expose stable context"

    restored = pm.PressureMemoryField()
    restored.from_dict(field.to_dict())
    assert restored.to_dict() == field.to_dict(), "field persistence must be deterministic"


if __name__ == "__main__":
    run()
    print("pressure memory OK")
