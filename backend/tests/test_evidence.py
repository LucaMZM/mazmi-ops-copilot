import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.evaluate_grounding import evaluate, main
from app.evidence import (
    ABSTENTION,
    ASSESSMENT_FAILURE,
    documentary_answer,
    missing_fact_relation,
    unverified_pay_condition,
)

CASES = json.loads((Path(__file__).parents[1] / "evals/grounding_cases.json").read_text())


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["name"])
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
    text, _, meta = documentary_answer(client, "Pregunta", [{"content": "Hecho"}], emit=events.append)
    expected = ASSESSMENT_FAILURE if meta["abstention_reason"] == "invalid_evidence_assessment" else ABSTENTION
    assert text == expected and meta["citations"] == []
    assert [e["text"] for e in events if e["type"] == "delta"] == [expected]


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


def test_grounding_report_covers_recovered_narrow_guards():
    report = evaluate()
    assert report["before_correct_abstentions"] == 1
    assert report["after_correct_abstentions"] == 21
    assert report["unanswerable_cases"] == 21
    assert report["false_abstentions"] == 0
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


@pytest.mark.parametrize("premise", [
    "", "No consta si el contrato contiene el anexo especial firmado.",
    "Quizás el contrato contiene el anexo especial firmado.",
    "¿El contrato contiene el anexo especial firmado?",
    "El contrato contiene otro anexo especial firmado.",
    "El contrato no contiene el anexo especial firmado.",
    "El contrato contiene el anexo especial firmado.\n",
])
def test_conditional_pay_requires_exact_asserted_premise_in_same_paragraph(premise):
    policy = "Si el contrato contiene el anexo especial firmado, el salario durante las vacaciones es de 2000 euros."
    assert unverified_pay_condition("¿Cuál es el salario durante las vacaciones?", premise + policy)


def test_exact_conditional_premise_only_allows_model_assessment():
    text = "El contrato contiene el anexo especial firmado. Si el contrato contiene el anexo especial firmado, el salario durante las vacaciones es de 2000 euros."
    question = "¿Cuál es el salario durante las vacaciones?"
    assert not unverified_pay_condition(question, text)
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return NS(status="completed", output=[], output_text='{"status":"insufficient","passage_ids":[]}')
    _, _, meta = documentary_answer(NS(responses=NS(create=create)), question, [{"content": text}])
    assert calls and meta["abstention_reason"] == "insufficient_evidence"


@pytest.mark.parametrize("text", [
    "Las vacaciones son 25 días.\nEn ese periodo el salario es de 2000 euros.",
    "Las vacaciones son 25 días. El curso son 5 días. En ese periodo el salario es de 2000 euros.",
    "Las vacaciones podrían ser 25 días. En ese periodo el salario es de 2000 euros.",
    "Las vacaciones son 25 días y el curso son 5 días. En ese periodo el salario es de 2000 euros.",
    "Las vacaciones son 25 días. En ese periodo el salario podría ser de 2000 euros.",
])
def test_anaphora_guard_refuses_other_paragraphs_ambiguity_and_uncertainty(text):
    assert missing_fact_relation("¿Cuál es el salario durante las vacaciones?", text)


def test_adjacent_anaphora_still_requires_sufficient_assessor():
    client = NS(responses=NS(create=lambda **kw: NS(
        status="completed", output=[], output_text='{"status":"insufficient","passage_ids":[]}'
    )))
    _, _, meta = documentary_answer(client, "¿Cuál es el salario durante las vacaciones?", [
        {"content": "Las vacaciones son 25 días. En ese periodo el salario es de 2000 euros."}
    ])
    assert meta["model_assessment_performed"]
    assert meta["abstention_reason"] == "insufficient_evidence"


def test_incomplete_assessor_is_not_reported_as_missing_documentation():
    client = NS(responses=NS(create=lambda **kw: NS(
        status="incomplete", output=[], output_text=""
    )))
    text, _, meta = documentary_answer(client, "Pregunta", [{"content": "Hecho"}])
    assert text == ASSESSMENT_FAILURE and text != ABSTENTION
    assert meta["abstention_reason"] == "incomplete_evidence_assessment"


@pytest.mark.parametrize("name,ids", [
    ("fabricated_passage", [1]), ("invented_assertion", [1]),
    ("selected_subset_missing_salary", [2]), ("selected_subset_wrong_relation", [2]),
])
def test_live_gold_uses_source_semantics_and_preserves_mock_labels(name, ids):
    client = NS(responses=NS(create=lambda **kw: NS(
        status="completed", output=[],
        output_text=json.dumps({"status":"sufficient", "passage_ids":ids})
    )))
    report = evaluate(client=client, case_names=[name], include_answers=False)
    result = report["cases"][0]
    assert result["mock_expected_abstention"] is True
    assert result["expected_abstention"] is False
    assert result["gold_label_mode"] == "live-semantic-override"
    assert result["gold_source_selection_correct"] and result["after_correct"]
    offline = evaluate(case_names=[name])["cases"][0]
    assert offline["expected_abstention"] is True and offline["after_correct"]


def test_failed_live_attempts_remain_in_answerability_denominators():
    def create(**kwargs):
        raise TimeoutError("private")
    report = evaluate(client=NS(responses=NS(create=create)), case_names=[
        "known_answer", "paraphrased_conflict"
    ])
    assert report["attempted_cases"] == 2 and report["completed_cases"] == 0
    assert report["answerable_cases"] == report["unanswerable_cases"] == 1
    assert report["answerable_provider_errors"] == report["unanswerable_provider_errors"] == 1
    assert report["accuracy_all_attempts"] == 0


def test_live_incomplete_assessor_does_not_count_as_correct_negative():
    client = NS(responses=NS(create=lambda **kw: NS(
        status="incomplete", output=[], output_text=""
    )))
    report = evaluate(client=client, case_names=["paraphrased_conflict"])
    assert report["attempted_cases"] == 1 and report["assessment_failures"] == 1
    assert report["after_correct_abstentions"] == 0 and report["accuracy_all_attempts"] == 0


def test_native_format_diagnostic_preserves_budget_and_never_exports_text(tmp_path):
    from app.diagnose_evidence import FormatOffDiagnostic, diagnose

    payload = FormatOffDiagnostic().payload({
        "model": "qwen3:4b", "instructions": "base", "input": [],
        "max_output_tokens": 2000, "text": {"format": {"schema": {"type": "object"}}},
    })
    assert "format" not in payload and payload["think"] is None
    assert payload["options"]["num_predict"] == 2000 and payload["keep_alive"] == 0
    assert payload["messages"][0]["content"].startswith("base\n")
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return NS(status="incomplete", output=[], output_text="private-generated-text")

    path = tmp_path / "diagnostic.json"
    report = diagnose(NS(responses=NS(create=create)), path)
    assert len(calls) == report["attempted_cases"] == 2
    assert report["answered_cases"] == 0
    assert "private-generated-text" not in path.read_text()
    assert "question" not in path.read_text() and "content" not in path.read_text()
