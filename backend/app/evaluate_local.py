"""Explicit, destructive-operation-free live Ollama RAG evaluation on an EMPTY dedicated DB.

Runs existing HTTP handlers with real PostgreSQL, embeddings and model assessment.
The database is intentionally retained for inspection. Never use a company database.
No network/model calls occur on import or in the unit tests for this module.
"""

import argparse
import json
import os
import re
import secrets
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

EVALS = Path(__file__).resolve().parents[1] / "evals"
REPO = Path(__file__).resolve().parents[2]


class EvaluationRequestError(RuntimeError):
    """Preserve the failed operation without IDs, query parameters or response bodies."""

    def __init__(self, method, path, status):
        super().__init__("Evaluation HTTP operation failed")
        route = path.partition("?")[0]
        known = {
            "/api/chat",
            "/api/actions",
            "/api/tickets",
            "/api/activity",
            "/api/documents",
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/workspace",
            "/api/auth/workspaces",
        }
        if route not in known:
            route = (
                "/api/actions/{action_id}/decision"
                if re.fullmatch(r"/api/actions/[0-9a-fA-F-]{36}/decision", route)
                else "/api/{unknown-operation}"
            )
        self.details = {
            "method": method if method in {"GET", "POST", "DELETE", "PUT", "PATCH"} else "UNKNOWN",
            "route_template": route,
            "http_status": status,
        }


def guard_configuration(settings):
    if (
        settings.app_env != "development"
        or settings.demo_mode
        or settings.generation_provider != "ollama"
        or settings.embedding_provider != "ollama"
    ):
        raise ValueError("Requires development, DEMO_MODE=false and both providers=ollama")
    database = conninfo_to_dict(settings.database_url).get("dbname", "")
    if not database.endswith(("_eval", "_local")):
        raise ValueError("Requires a dedicated database ending in _eval or _local")
    return database


def assert_empty_database(conn):
    # Check ALL application tables before migrations, including unknown application tables.
    # A pre-existing migration ledger alone is harmless; actual records are not.
    tables = conn.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') "
        "AND schemaname NOT LIKE 'pg_toast%' AND tablename<>'schema_migrations'"
    ).fetchall()
    for schema, table in tables:
        if conn.execute(
            sql.SQL("SELECT 1 FROM {}.{} LIMIT 1").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchone():
            raise ValueError("Evaluation requires an empty database; existing data was preserved")


def load_cases(path=EVALS / "local_cases.json"):
    dataset = json.loads(Path(path).read_text())
    documents, questions = dataset["documents"], dataset["questions"]
    filenames = [document["filename"] for document in documents]
    if len(documents) != 4 or len(questions) != 8 or len(set(filenames)) != 4:
        raise ValueError("Expected four unique documents and eight questions")
    if len({case["name"] for case in questions}) != 8:
        raise ValueError("Evaluation case names must be unique")
    for case in questions:
        if not set(case["expected_documents"]).issubset(filenames):
            raise ValueError("Unknown expected fixture document")
        if case["expected_abstention"] != (not case["expected_documents"]):
            raise ValueError("Abstention and source expectations disagree")
    return dataset


def source_metrics(expected_documents, retrieved, cited):
    expected = set(expected_documents)
    ranked = list(dict.fromkeys(retrieved))  # Document-level, not chunk-level metrics.
    return {
        "document_recall_at_6": len(expected.intersection(ranked)) / len(expected)
        if expected
        else None,
        "document_reciprocal_rank": next(
            (1 / rank for rank, name in enumerate(ranked, 1) if name in expected), 0.0
        )
        if expected
        else None,
        "all_expected_documents_cited": expected.issubset(cited) if expected else None,
        "unexpected_documents_cited": sorted(set(cited) - expected),
    }


def prepare_credentials_file(path):
    """Reserve a private, new file outside this or any other Git worktree."""
    path = Path(path).expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("Credentials file must be outside the repository")
    if any((parent / ".git").exists() for parent in (path.parent, *path.parents)):
        raise ValueError("Credentials file must be outside Git worktrees")
    # O_EXCL also prevents silently replacing an existing file or following a symlink.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, "w")


def summarize(results):
    complete = [case for case in results if "http_status" not in case]
    positives = [case for case in complete if not case["expected_abstention"]]
    negatives = [case for case in complete if case["expected_abstention"]]
    return {
        "attempted_questions": len(results),
        "completed_questions": len(complete),
        "http_errors": len(results) - len(complete),
        "answerable_cases": len(positives),
        "unanswerable_cases": len(negatives),
        "correct_abstentions": sum(case["abstained"] for case in negatives),
        "false_abstentions": sum(case["abstained"] for case in positives),
        "mean_document_recall_at_6": statistics.mean(
            case["document_recall_at_6"] for case in positives
        )
        if positives
        else None,
        "document_mrr": statistics.mean(case["document_reciprocal_rank"] for case in positives)
        if positives
        else None,
        "answerable_cases_with_all_gold_documents_cited": sum(
            case["all_expected_documents_cited"] for case in positives
        ),
        "all_returned_citation_ids_valid": all(case["citation_ids_valid"] for case in complete)
        if complete
        else None,
        "mean_retrieval_ms_including_embedding": statistics.mean(
            case["retrieval_ms"] for case in complete
        )
        if complete
        else None,
    }


def run(*, credentials_file=None):
    from fastapi.testclient import TestClient

    from .config import settings

    database = guard_configuration(settings)
    dataset = load_cases()
    # Do not print settings, connection strings, provider exceptions or HTTP bodies.
    with psycopg.connect(settings.database_url, autocommit=True, connect_timeout=10) as guard:
        if guard.execute("SELECT current_database()").fetchone()[0] != database:
            raise ValueError("Connected database does not match the dedicated evaluation database")
        if not guard.execute("SELECT pg_try_advisory_lock(7348223)").fetchone()[0]:
            raise ValueError("Another local evaluation is already running")
        guard.execute("SET statement_timeout = '10s'")
        assert_empty_database(guard)
        if guard.execute("SELECT current_schema()").fetchone()[0] != "public":
            raise ValueError("Evaluation requires the standard public schema")
        from .migrate import migrate

        migrate()
        from .main import app, get_conn
        from .rag import embedding_collection

        origin = settings.cors_origins.split(",")[0].strip()
        email = "evaluation-" + secrets.token_hex(5) + "@mazmi.local"
        password = secrets.token_urlsafe(24)
        headers = {"Origin": origin}
        checks = {}
        results = []
        ingestion = []
        journey_failure = None
        with TestClient(app, headers=headers) as api:

            def request(method, path, *, expected=200, **kwargs):
                response = api.request(method, path, **kwargs)
                if response.status_code != expected:
                    raise EvaluationRequestError(method, path, response.status_code)
                return response.json()

            registered = request(
                "POST",
                "/api/auth/register",
                expected=201,
                json={
                    "email": email,
                    "password": password,
                    "workspace_name": "MAZMI · Evaluación local",
                },
            )
            workspace = registered["workspace_id"]
            request("POST", "/api/auth/logout")
            request("POST", "/api/auth/login", json={"email": email, "password": password})
            checks["registration_and_login"] = True
            if credentials_file:
                json.dump(
                    {"email": email, "password": password, "workspace_id": workspace},
                    credentials_file,
                )
                credentials_file.flush()
            for document in dataset["documents"]:
                started = time.perf_counter()
                response = api.post(
                    "/api/documents",
                    files={"file": (document["filename"], document["text"].encode(), "text/plain")},
                )
                ingestion.append(
                    {
                        "fixture": document["filename"],
                        "http_status": response.status_code,
                        "ready": response.status_code == 200
                        and response.json().get("status") == "ready",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                )
            checks["all_four_documents_indexed"] = all(item["ready"] for item in ingestion)
            for case in dataset["questions"]:
                started = time.perf_counter()
                response = api.post("/api/chat", json={"message": case["question"], "mode": "ASK"})
                result = {
                    "name": case["name"],
                    "expected_abstention": case["expected_abstention"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                if response.status_code != 200:
                    results.append({**result, "http_status": response.status_code})
                    continue
                body = response.json()
                with get_conn() as conn:
                    row = conn.execute(
                        "SELECT details FROM audit_events WHERE workspace_id=%s AND conversation_id=%s "
                        "AND event_type='chat.completed' ORDER BY id DESC LIMIT 1",
                        (workspace, body["conversation_id"]),
                    ).fetchone()
                    meta = row[0]
                    valid_chunks = {
                        (chunk[0], str(chunk[1]), chunk[2], chunk[3])
                        for chunk in conn.execute(
                            "SELECT c.id,c.document_id,d.filename,c.page_number FROM document_chunks c "
                            "JOIN documents d ON d.id=c.document_id WHERE c.workspace_id=%s "
                            "AND d.workspace_id=%s AND d.status='ready'",
                            (workspace, workspace),
                        ).fetchall()
                    }
                refs = [int(value) for value in re.findall(r"\[(\d+)\]", body["answer"])]
                sources = body["sources"]
                valid_ids = all(1 <= ref <= len(sources) for ref in refs)
                valid_sources = all(
                    (s["chunk_id"], s["document_id"], s["filename"], s["page"]) in valid_chunks
                    for s in sources
                )
                cited = [sources[ref - 1]["filename"] for ref in refs if 1 <= ref <= len(sources)]
                result.update(
                    {
                        "abstained": bool(meta.get("abstention_reason")),
                        "abstention_reason": meta.get("abstention_reason"),
                        "evidence_policy": meta.get("evidence_policy"),
                        "citation_ids_valid": valid_ids and valid_sources,
                        "citation_count": len(refs),
                        "retrieved_documents": list(dict.fromkeys(s["filename"] for s in sources)),
                        "cited_documents": list(dict.fromkeys(cited)),
                        "retrieval_ms": meta["retrieval_ms"],
                        "retrieval_strategy": meta["retrieval"]["strategy"],
                        "vector_candidates": meta["retrieval"].get("vector_candidates", 0),
                        "lexical_candidates": meta["retrieval"].get("lexical_candidates", 0),
                        "unexpected_proposal": body["pending_action"] is not None,
                        **source_metrics(
                            case["expected_documents"], [s["filename"] for s in sources], cited
                        ),
                    }
                )
                results.append(result)
            checks["ask_never_mutated"] = not request("GET", "/api/actions") and not request(
                "GET", "/api/tickets"
            )
            # Existing empty-workspace and membership checks, with no model data leakage.
            empty = request(
                "POST", "/api/auth/workspaces", expected=201, json={"name": "MAZMI · Vacío"}
            )["id"]
            request("POST", "/api/auth/workspace", json={"workspace_id": empty})
            empty_answer = request(
                "POST", "/api/chat", json={"message": dataset["questions"][0]["question"]}
            )
            checks["empty_workspace_no_sources_or_action"] = (
                not empty_answer["sources"] and empty_answer["pending_action"] is None
            )
            checks["empty_workspace_no_documents_or_activity_leak"] = not request(
                "GET", "/api/documents"
            ) and all(
                event["type"] == "chat.completed" for event in request("GET", "/api/activity")
            )
            request("POST", "/api/auth/workspace", json={"workspace_id": workspace})
            try:
                journey(api, request, get_conn, app, headers, workspace, checks)
            except EvaluationRequestError as exc:
                checks["journey_completed_without_http_errors"] = False
                journey_failure = exc.details
            except RuntimeError:
                checks["journey_completed_without_http_errors"] = False
                journey_failure = {
                    "operation": "fixture_setup_or_journey",
                    "error_type": "RuntimeError",
                }
            collection = embedding_collection()
        return {
            "mode": "live-ollama-http-pipeline-real-postgresql",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "generation_model": settings.generation_model,
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.vector_dimensions,
            "embedding_collection": collection,
            "fixtures": "local_cases.json; four fictitious documents / eight questions",
            "ingestion": ingestion,
            "cases": results,
            "summary": summarize(results),
            "journey_checks": checks,
            "journey_failure": journey_failure,
            "limitations": [
                "Gold document coverage and citation validity do not prove semantic entailment or full answer correctness.",
                "Abstention labels are controlled fixture expectations, not general model accuracy.",
                "Recall/MRR are document-level on answerable fixtures, K=6 chunks; latency includes query embedding.",
                "No baseline model comparison, no cloud provider, no mocks, no voice or browser timing measured.",
                "Only newly created fictitious records are used; database retained, never reset or cleaned automatically.",
            ],
        }


def journey(api, request, get_conn, app, headers, workspace, checks):
    from fastapi.testclient import TestClient

    def propose():
        response = request(
            "POST",
            "/api/chat",
            json={
                "message": "Crea un ticket para revisar una pérdida de material crítico en el almacén Norte. Prioridad alta.",
                "mode": "DO",
            },
        )
        return response["pending_action"]

    first = propose()
    checks["do_proposal_before_execution"] = bool(first) and not request("GET", "/api/tickets")
    if not first:
        checks["approval_executes_once"] = False
        checks["rejection_never_executes"] = False
        checks["foreign_requester_cannot_approve"] = False
        return
    action = f"/api/actions/{first['id']}/decision"
    with TestClient(app, headers=headers) as other:
        peer_email = "evaluation-peer-" + secrets.token_hex(5) + "@mazmi.local"
        peer = other.post(
            "/api/auth/register",
            json={
                "email": peer_email,
                "password": secrets.token_urlsafe(24),
                "workspace_name": "MAZMI · Ajeno",
            },
        )
        if peer.status_code != 201:
            raise RuntimeError("Peer fixture registration failed")
        checks["foreign_workspace_cannot_approve"] = (
            other.post(action, json={"approved": True}).status_code == 404
        )
        checks["foreign_workspace_cannot_read_documents"] = other.get("/api/documents").json() == []
        # Fictitious fixture membership only; there is no membership-management endpoint.
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO workspace_members(user_id,workspace_id) SELECT id,%s FROM users WHERE email=%s",
                (workspace, peer_email),
            )
        if other.post("/api/auth/workspace", json={"workspace_id": workspace}).status_code != 200:
            raise RuntimeError("Peer fixture workspace selection failed")
        checks["foreign_requester_cannot_approve"] = (
            other.post(action, json={"approved": True}).status_code == 404
            and other.get("/api/actions").json() == []
        )
    approved = api.post(action, json={"approved": True})
    checks["approval_executes_once"] = (
        approved.status_code == 200
        and api.post(action, json={"approved": True}).status_code == 409
        and len(request("GET", "/api/tickets")) == 1
    )
    second = propose()
    if second:
        rejection = f"/api/actions/{second['id']}/decision"
        rejected = api.post(rejection, json={"approved": False})
        checks["rejection_never_executes"] = (
            rejected.status_code == 200
            and api.post(rejection, json={"approved": True}).status_code == 409
            and len(request("GET", "/api/tickets")) == 1
        )
    else:
        checks["rejection_never_executes"] = False
    read = request(
        "POST", "/api/chat", json={"message": "Lista los tickets del workspace", "mode": "ASK"}
    )
    with get_conn() as conn:
        read_audit = conn.execute(
            "SELECT details FROM audit_events WHERE workspace_id=%s AND conversation_id=%s "
            "AND event_type='chat.completed' ORDER BY id DESC LIMIT 1",
            (workspace, read["conversation_id"]),
        ).fetchone()[0]
    checks["ask_read_tool_without_write"] = (
        read["pending_action"] is None
        and not read["sources"]
        and any(tool.get("name") == "get_tickets" for tool in read_audit["tools"])
        and len(request("GET", "/api/tickets")) == 1
    )
    events = [event["type"] for event in request("GET", "/api/activity")]
    checks["proposal_execution_rejection_audited"] = (
        events.count("action.proposed") == 2
        and events.count("action.executed") == 1
        and events.count("action.rejected") == 1
    )


def fixture_checks_passed(report):
    summary = report["summary"]
    return (
        summary["completed_questions"] == 8
        and summary["http_errors"] == 0
        and summary["correct_abstentions"] == summary["unanswerable_cases"] == 4
        and summary["false_abstentions"] == 0
        and summary["answerable_cases_with_all_gold_documents_cited"] == 4
        and summary["all_returned_citation_ids_valid"] is True
        and all(report["journey_checks"].values())
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Required consent to use installed Ollama models"
    )
    parser.add_argument("--output", type=Path, required=True, help="Public sanitized JSON result")
    parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Optional NEW private 0600 file outside Git, for later browser login",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; no model download or cloud fallback is performed")
    credentials = None
    try:
        if args.credentials_file:
            credentials = prepare_credentials_file(args.credentials_file)
        report = run(credentials_file=credentials)
        report["automated_fixture_checks_passed"] = fixture_checks_passed(report)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {"summary": report["summary"], "journey_checks": report["journey_checks"]}, indent=2
            )
        )
        if not report["automated_fixture_checks_passed"]:
            raise SystemExit(2)
    except (OSError, ValueError, RuntimeError, psycopg.Error) as exc:
        # Type only: database/provider exception messages can contain URLs or credentials.
        print(json.dumps({"evaluation_error": type(exc).__name__, "report_complete": False}))
        raise SystemExit(1) from None
    finally:
        if credentials:
            credentials.close()


if __name__ == "__main__":
    main()
