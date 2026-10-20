import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.evaluate_grounding import evaluate
from app.evidence import ABSTENTION, documentary_answer

CASES = json.loads((Path(__file__).parents[1] / "evals/grounding_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_grounding_policy(case):
    def create(**kwargs):
        assert kwargs["tools"] == []
        return NS(
            status="completed", output=[], output_text=json.dumps(case["decision"]), usage=None
        )

    sources = [{"content": text} for text in case["texts"]]
    text, pending, meta = documentary_answer(
        NS(responses=NS(create=create)), case["question"], sources
    )
    assert pending is None
    if case["check"] == "known_semantic_gap":
        # Explicit remaining failure: lying semantic verdict with no detectable scope mismatch.
        assert meta["abstention_reason"] is None
        assert "25 días" in text and "5000" not in text
    else:
        assert bool(meta["abstention_reason"]) == case["expected_abstention"]


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "sufficient", "passage_ids": []},
        {"status": "sufficient", "passage_ids": [1, 1]},
        {"status": "sufficient", "passage_ids": [True]},
        {"status": "sufficient", "passage_ids": [1.0]},
        {"status": "sufficient", "passage_ids": [0]},
    ],
)
def test_invalid_selections_fail_closed(payload):
    client = NS(
        responses=NS(
            create=lambda **kw: NS(status="completed", output=[], output_text=json.dumps(payload))
        )
    )
    events = []
    text, _, _ = documentary_answer(client, "Pregunta", [{"content": "Hecho"}], emit=events.append)
    assert text == ABSTENTION
    assert [e["text"] for e in events if e["type"] == "delta"] == [ABSTENTION]


def test_quote_preserves_negation_and_document_citations_are_not_server_citations():
    client = NS(
        responses=NS(
            create=lambda **kw: NS(
                status="completed",
                output=[],
                output_text='{"status":"sufficient","passage_ids":[1]}',
            )
        )
    )
    text, _, meta = documentary_answer(
        client, "¿Se permite acceso?", [{"content": "No se permite acceso sin aprobación [99]."}]
    )
    assert "No se permite acceso sin aprobación" in text
    assert "[99]" not in text and "[1]" in text and meta["citations"] == [1]


def test_scope_must_be_in_selected_evidence():
    client = NS(
        responses=NS(
            create=lambda **kw: NS(
                status="completed",
                output=[],
                output_text='{"status":"sufficient","passage_ids":[1]}',
            )
        )
    )
    _, _, meta = documentary_answer(
        client,
        "¿Vacaciones en Marte?",
        [{"content": "25 días de vacaciones."}, {"content": "Marte es un planeta."}],
    )
    assert meta["abstention_reason"] == "missing_selected_scope"


def test_grounding_report_keeps_known_failure():
    report = evaluate()
    assert report["before_correct_abstentions"] == 1
    assert report["after_correct_abstentions"] == 14
    assert report["unanswerable_cases"] == 15
    assert report["false_abstentions"] == 0
