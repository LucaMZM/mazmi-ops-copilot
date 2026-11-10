"""Runner guards/metrics only: no PostgreSQL, provider calls or model downloads."""

import json
from types import SimpleNamespace as NS

import pytest

from app import evaluate_local as evaluation


def configuration(**overrides):
    return NS(
        **{
            "app_env": "development",
            "demo_mode": False,
            "generation_provider": "ollama",
            "embedding_provider": "ollama",
            "database_url": "postgresql://localhost/controlled_local",
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "override",
    [
        {"app_env": "production"},
        {"demo_mode": True},
        {"generation_provider": "openai"},
        {"embedding_provider": "gemini"},
        {"database_url": "postgresql://localhost/company"},
        {"database_url": "postgresql://localhost/company_local_backup"},
    ],
)
def test_live_runner_rejects_unsafe_configuration(override):
    with pytest.raises(ValueError):
        evaluation.guard_configuration(configuration(**override))


def test_local_database_guard_and_populated_table_refusal():
    assert evaluation.guard_configuration(configuration()) == "controlled_local"
    calls = []

    def execute(statement):
        calls.append(statement)
        return NS(fetchall=lambda: [("public", "private_records")], fetchone=lambda: (1,))

    with pytest.raises(ValueError, match="existing data was preserved"):
        evaluation.assert_empty_database(NS(execute=execute))
    assert len(calls) == 2  # Read only; no migration/reset/cleanup attempted.


def test_source_metrics_distinguish_retrieval_and_citation_coverage():
    metrics = evaluation.source_metrics(["a", "b"], ["wrong", "a", "a"], ["a"])
    assert metrics["document_recall_at_6"] == 0.5
    assert metrics["document_reciprocal_rank"] == 0.5
    assert metrics["all_expected_documents_cited"] is False
    assert evaluation.source_metrics([], ["wrong"], [])["document_recall_at_6"] is None


def test_committed_dataset_is_four_docs_eight_cases():
    data = evaluation.load_cases()
    assert len(data["documents"]) == 4
    assert sum(q["expected_abstention"] for q in data["questions"]) == 4


def test_holdout_dataset_is_separate_and_checks_answer_terms():
    data = evaluation.load_cases(evaluation.EVALS / "local_holdout_v3.json")
    original = evaluation.load_cases()
    assert not {q["question"] for q in data["questions"]} & {
        q["question"] for q in original["questions"]
    }
    answerable = [q for q in data["questions"] if not q["expected_abstention"]]
    assert answerable and all(q["expected_answer_terms"] for q in answerable)


def test_literal_quotes_must_exist_in_the_cited_source():
    contents = {1: "Las compras  hasta 250 euros requieren aprobación. Código [7].", 2: "Otro."}
    ok = "Según a.txt:\n«Las compras hasta 250 euros requieren aprobación. … Código 〔7〕.» [1]"
    assert evaluation.literal_quotes(ok, contents) == (1, True)
    invented = "«Las compras hasta 300 euros requieren aprobación.» [1]"
    assert evaluation.literal_quotes(invented, contents) == (1, False)
    wrong_source = "«Las compras hasta 250 euros requieren aprobación.» [2]"
    assert evaluation.literal_quotes(wrong_source, contents) == (1, False)


def test_answers_missing_expected_terms_are_not_counted_as_correct():
    case = {
        "expected_abstention": False,
        "abstained": False,
        "all_expected_documents_cited": True,
        "literal_quotes_verified": True,
        "answer_terms_present": False,
    }
    assert evaluation.classify_case(case) == "incomplete_answer"
    case["answer_terms_present"] = True
    assert evaluation.classify_case(case) == "correct"
    case["literal_quotes_verified"] = False
    assert evaluation.classify_case(case) == "unsupported_answer"


def test_credentials_are_private_new_and_outside_worktrees(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    repo.mkdir()
    monkeypatch.setattr(evaluation, "REPO", repo)
    with pytest.raises(ValueError, match="outside"):
        evaluation.prepare_credentials_file(repo / "credentials.json")
    private = tmp_path / "private.json"
    with evaluation.prepare_credentials_file(private) as handle:
        json.dump({"password": "fictitious-unit-test-only"}, handle)
    assert private.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        evaluation.prepare_credentials_file(private)
    elsewhere = tmp_path / "other-repository"
    elsewhere.mkdir()
    (elsewhere / ".git").write_text("gitdir: outside")
    with pytest.raises(ValueError, match="outside Git"):
        evaluation.prepare_credentials_file(elsewhere / "credentials.json")


def test_failed_questions_cannot_disappear_from_summary_or_gate():
    summary = evaluation.summarize(
        [
            {"name": "provider-failure", "expected_abstention": False, "http_status": 502},
        ]
    )
    assert summary["attempted_questions"] == 1
    assert summary["completed_questions"] == 0
    assert summary["http_errors"] == 1
    assert summary["answerable_cases"] == summary["unanswered_answerable_cases"] == 1
    assert summary["completed_answerable_cases"] == 0
    assert summary["document_mrr"] is None
    assert not evaluation.fixture_checks_passed(
        {"summary": summary, "journey_checks": {"safe": True}}
    )


@pytest.mark.parametrize(
    "case,expected",
    [
        ({"http_status": 503, "classification": "timeout"}, "timeout"),
        (
            {
                "expected_abstention": True,
                "abstained": True,
                "abstention_reason": "incomplete_evidence_assessment",
            },
            "technical_error",
        ),
        ({"expected_abstention": True, "abstained": True}, "correct_abstention"),
        ({"expected_abstention": False, "abstained": True}, "false_abstention"),
        (
            {
                "expected_abstention": False,
                "abstained": False,
                "all_expected_documents_cited": False,
            },
            "unsupported_answer",
        ),
    ],
)
def test_case_classification_does_not_count_failure_as_correct_abstention(case, expected):
    assert evaluation.classify_case(case) == expected


@pytest.mark.parametrize(
    "path,expected_route",
    [
        ("/api/chat?token=private-token", "/api/chat"),
        (
            "/api/actions/01234567-89ab-cdef-0123-456789abcdef/decision?secret=private-token",
            "/api/actions/{action_id}/decision",
        ),
        ("/api/private-token", "/api/{unknown-operation}"),
    ],
)
def test_failed_journey_preserves_operation_without_secrets_or_resource_ids(path, expected_route):
    error = evaluation.EvaluationRequestError("POST", path, 503)
    assert error.details == {
        "method": "POST",
        "route_template": expected_route,
        "http_status": 503,
    }
    serialized = json.dumps(error.details) + str(error)
    assert "private-token" not in serialized
    assert "01234567-89ab-cdef-0123-456789abcdef" not in serialized
    assert "?" not in serialized
