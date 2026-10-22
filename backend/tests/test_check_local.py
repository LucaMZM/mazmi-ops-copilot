import json

import httpx
import pytest

from app import check_local, rag
from app.config import settings
from app.providers import Ollama


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "generation_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_dimensions", 768)


def test_smoke_refuses_demo_and_nonlocal_provider(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        check_local.run_checks()
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    with pytest.raises(RuntimeError, match="only permits Ollama"):
        check_local.run_checks()


def fixture_server(request):
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"version": "fixture"})
    if request.url.path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:4b", "digest": "chat-v1", "size": 2000},
                    {"name": "embeddinggemma:latest", "digest": "embed-v1", "size": 500},
                ]
            },
        )
    body = json.loads(request.content)
    if request.url.path == "/api/show":
        return httpx.Response(
            200,
            json={
                "capabilities": ["embedding"] if body["model"] == "embeddinggemma" else ["tools"],
                "model_info": {"gemma3.embedding_length": 768},
            },
        )
    if request.url.path == "/api/embed":
        return httpx.Response(200, json={"embeddings": [[1.0] + [0.0] * 767]})
    if body.get("stream"):
        return httpx.Response(
            200, text='{"message":{"content":"OK"},"done":false}\n{"message":{},"done":true}\n'
        )
    message = {"content": "Hola 1"}
    if "format" in body:
        message["content"] = '{"status":"sufficient","passage_ids":[1]}'
    if body.get("tools"):
        message = {"tool_calls": [{"function": {"name": "local_probe", "arguments": {"value": 1}}}]}
    return httpx.Response(200, json={"message": message, "done": True})


def test_smoke_runs_all_capabilities_without_tools_or_database(local, monkeypatch):
    client = Ollama(httpx.MockTransport(fixture_server))
    monkeypatch.setattr(rag, "client", client)
    report = check_local.run_checks(client)
    assert report["status"] == "passed" and len(report["checks"]) == 6
    assert report["checks"]["tool_proposal_roundtrip"]["tool_executed"] is False
    assert report["checks"]["early_close_recovery"]["gpu_cancellation"] == "not_measured"
    assert report["checks"]["embeddings"]["dimensions"] == 768
    assert all(check["duration_ms"] >= 0 for check in report["checks"].values())


def test_manual_readiness_is_bounded_to_schema_and_embeddings(local, monkeypatch):
    requests = []

    def server(request):
        requests.append(request.url.path)
        return fixture_server(request)

    client = Ollama(httpx.MockTransport(server))
    monkeypatch.setattr(rag, "client", client)
    report = check_local.run_checks(client, full=False)
    assert report["status"] == "passed" and report["scope"] == "readiness"
    assert set(report["checks"]) == {"structured_output", "embeddings"}
    assert requests.count("/api/chat") == 1 and requests.count("/api/embed") == 1


def test_smoke_fails_before_inference_when_missing_models(local):
    def server(request):
        assert request.url.path in {"/api/version", "/api/tags"}
        return httpx.Response(200, json={"version": "fixture", "models": []})

    report = check_local.run_checks(Ollama(httpx.MockTransport(server)))
    assert report["status"] == "failed"
    assert "not installed" in report["error"] and report["checks"] == {}


def test_smoke_main_returns_nonzero_for_failed_report(monkeypatch, capsys):
    monkeypatch.setattr(check_local, "run_checks", lambda: {"status": "failed"})
    with pytest.raises(SystemExit) as exc:
        check_local.main([])
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"status": "failed"}


def test_smoke_targeted_checks_are_explicit_and_do_not_repeat_inference(local, monkeypatch):
    requests = []

    def server(request):
        requests.append(request.url.path)
        return fixture_server(request)

    client = Ollama(httpx.MockTransport(server))
    monkeypatch.setattr(rag, "client", client)
    report = check_local.run_checks(client, check_names=("early_close_recovery",))
    assert report["status"] == "passed" and report["scope"] == "selected"
    assert set(report["checks"]) == {"early_close_recovery"}
    assert requests.count("/api/chat") == 2 and "/api/embed" not in requests


def test_smoke_unknown_check_refuses_inference(local):
    report = check_local.run_checks(
        Ollama(httpx.MockTransport(fixture_server)), check_names=("unknown",)
    )
    assert report["status"] == "failed" and report["checks"] == {}


def test_smoke_cli_selection_is_explicit(monkeypatch, capsys):
    seen = []

    def run_checks(**kwargs):
        seen.append(kwargs)
        return {"status": "passed", "scope": "selected"}

    monkeypatch.setattr(check_local, "run_checks", run_checks)
    check_local.main(["--check", "early_close_recovery"])
    assert seen == [{"check_names": ("early_close_recovery",)}]
    assert json.loads(capsys.readouterr().out)["scope"] == "selected"
