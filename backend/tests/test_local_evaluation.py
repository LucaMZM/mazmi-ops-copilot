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
    assert summary["document_mrr"] is None
    assert not evaluation.fixture_checks_passed(
        {"summary": summary, "journey_checks": {"safe": True}}
    )


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
