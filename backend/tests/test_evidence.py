import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.evaluate_grounding import evaluate, main
from app.evidence import ABSTENTION, documentary_answer, missing_fact_relation

CASES = json.loads((Path(__file__).parents[1] / "evals/grounding_cases.json").read_text())


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            id=case["name"],
            marks=pytest.mark.xfail(
                strict=True,
                reason="Visible semantic applicability gap or conservative implicit-reference refusal",
            )
            if case["check"] in {"known_semantic_gap", "known_conservative_refusal"}
            else (),
        )
        for case in CASES
    ],
)
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
    assert bool(meta["abstention_reason"]) == case["expected_abstention"]
    assert all(1 <= citation <= len(sources) for citation in meta["citations"])
    if not meta["abstention_reason"]:
        assert all(sources[i - 1]["content"] in text for i in meta["selected_passage_ids"])


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
    assert report["after_correct_abstentions"] == 20
    assert report["unanswerable_cases"] == 21
    assert report["false_abstentions"] == 1
    assert report["answerable_cases"] == 6
    assert report["all_citation_ids_valid"]
    historical = report["historical_extractive_v2_comparison"]
    assert historical["matching_cases"] == 19
    assert historical["previous_correct_abstentions"] == 14
    assert historical["current_correct_abstentions"] == 15
    assert historical["current_false_abstentions"] == 0


def test_relation_guard_does_not_join_sources_or_treat_keywords_as_a_relation():
    question = "¿Cuál es el salario durante las vacaciones?"
    assert missing_fact_relation(question, "El salario depende de ventas.\nHay vacaciones.")
    assert missing_fact_relation(question, "El salario durante\nlas vacaciones es de 2000 euros.")
    assert not missing_fact_relation(question, "Durante las vacaciones se mantiene el salario.")
    assert not missing_fact_relation("¿Cuántos días hay?", "Las vacaciones son 25 días.")


def test_live_evaluation_does_not_leak_provider_errors_or_answers():
    def create(**kwargs):
        raise RuntimeError("private-document-and-secret")

    report = evaluate(
        client=NS(responses=NS(create=create)),
        case_names=["known_answer"],
        include_answers=False,
    )
    assert report["provider_errors"] == 1
    assert report["completed_cases"] == 0
    assert report["answer_precision"] is None
    assert "private-document-and-secret" not in json.dumps(report)
    assert "answer" not in report["cases"][0]


def test_live_evaluation_refuses_cloud_or_demo(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr("sys.argv", ["evaluate_grounding", "--live"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_unknown_evaluation_case_fails_instead_of_reporting_empty_success():
    with pytest.raises(ValueError, match="Unknown evaluation case"):
        evaluate(case_names=["nonexistent-case"])
