import json

import httpx
import pytest

from app.config import Settings, settings
from app.gemini import Gemini
from app.providers import ProviderQuotaExceeded, ProviderUnavailable


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "mock-secret-not-real")
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr(settings, "embedding_provider", "gemini")


def answer(parts=None, reason="STOP"):
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": parts or [{"text": "OK"}]},
                "finishReason": reason,
            }
        ]
    }


def test_defaults_and_missing_key(monkeypatch):
    defaults = Settings(_env_file=None)
    assert defaults.generation_provider == defaults.embedding_provider == "gemini"
    assert defaults.vector_dimensions == 768
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(ProviderUnavailable, match="GEMINI_API_KEY"):
        Gemini().create(model="test", input=[{"role": "user", "content": "Test"}])


def test_sdk_structured_and_signed_tool_roundtrip(gemini):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["x-goog-api-key"] == "mock-secret-not-real"
        if len(requests) == 1:
            assert body["generationConfig"]["responseMimeType"] == "application/json"
            return httpx.Response(200, json=answer([{"text": '{"status":"insufficient"}'}]))
        if len(requests) == 2:
            assert body["tools"][0]["functionDeclarations"][0]["name"] == "get_tickets"
            return httpx.Response(
                200,
                json=answer(
                    [
                        {
                            "functionCall": {
                                "name": "get_tickets",
                                "args": {"limit": 1},
                                "id": "abc",
                            },
                            "thoughtSignature": "c2lnbmVk",
                        }
                    ]
                ),
            )
        assert body["contents"][1]["parts"][0]["thoughtSignature"] == "c2lnbmVk"
        assert body["contents"][2]["parts"][0]["functionResponse"]["name"] == "get_tickets"
        return httpx.Response(200, json=answer())

    client = Gemini(httpx.MockTransport(handler))
    inputs = [{"role": "user", "content": "Consulta mis tickets"}]
    result = client.create(
        model=settings.generation_model,
        input=inputs,
        text={
            "format": {"schema": {"type": "object", "properties": {"status": {"type": "string"}}}}
        },
    )
    assert result.status == "completed"
    result = client.create(
        model=settings.generation_model,
        input=inputs,
        tools=[
            {
                "name": "get_tickets",
                "description": "Read",
                "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            }
        ],
    )
    assert result.output[0].call_id == "abc"
    result = client.create(
        model=settings.generation_model,
        input=[
            *inputs,
            *result.output,
            {"type": "function_call_output", "call_id": "abc", "output": "[]"},
        ],
    )
    assert result.output_text == "OK"
    assert len(requests) == 3


@pytest.mark.parametrize("reason", ["STOP", "MAX_TOKENS", "SAFETY"])
def test_sdk_stream_finish(gemini, reason):
    def handler(request):
        frames = [answer([{"text": "Hola"}], None), answer([{"text": " mundo"}], reason)]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join("data: " + json.dumps(f) + "\n\n" for f in frames),
        )

    with Gemini(httpx.MockTransport(handler)).create(
        model=settings.generation_model, input=[{"role": "user", "content": "Test"}], stream=True
    ) as stream:
        events = list(stream)
    assert events[-1].response.output_text == "Hola mundo"
    assert events[-1].type == ("response.completed" if reason == "STOP" else "response.incomplete")


def test_sdk_truncated_stream(gemini):
    client = Gemini(
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="data: " + json.dumps(answer(reason=None)) + "\n\n",
            )
        )
    )
    with (
        pytest.raises(ProviderUnavailable, match="interrumpido"),
        client.create(
            model=settings.generation_model,
            input=[{"role": "user", "content": "Test"}],
            stream=True,
        ) as stream,
    ):
        list(stream)


@pytest.mark.parametrize("status", [429, 400, 401, 403, 500, 503])
def test_sdk_errors_sanitized_no_retry(gemini, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {"code": status, "message": "mock-secret-not-real PRIVATE DOCUMENT"}},
        )

    with pytest.raises(ProviderQuotaExceeded if status == 429 else ProviderUnavailable) as exc:
        Gemini(httpx.MockTransport(handler)).create(
            model=settings.generation_model, input=[{"role": "user", "content": "Test"}]
        )
    assert "mock-secret" not in str(exc.value) and "PRIVATE" not in str(exc.value)
    assert len(calls) == 1


def test_sdk_embeddings_separate_inputs_prefixes_and_identity(gemini, monkeypatch):
    from app import rag

    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200, json={"embeddings": [{"values": [1.0] + [0.0] * 767} for _ in body["requests"]]}
        )

    monkeypatch.setattr(rag, "client", Gemini(httpx.MockTransport(handler)))
    assert len(rag.embed_texts(["A", "B"])) == 2
    assert len(rag.embed_query("A")) == 768
    assert requests[0]["requests"][0]["content"]["parts"][0]["text"] == "title: none | text: A"
    assert (
        requests[1]["requests"][0]["content"]["parts"][0]["text"]
        == "task: search result | query: A"
    )
    assert "gemini:gemini-embedding-2:768:" in rag.embedding_collection()
    assert requests[0]["requests"][0]["outputDimensionality"] == 768


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("private"), httpx.ConnectError("private")])
def test_network_failure_is_sanitized_without_retry(gemini, failure):
    calls = []

    def server(request):
        calls.append(request)
        raise failure

    with pytest.raises(ProviderUnavailable) as result:
        Gemini(httpx.MockTransport(server)).create(
            model=settings.generation_model, input=[{"role": "user", "content": "Hi"}]
        )
    assert "private" not in str(result.value) and len(calls) == 1
