import json
from types import SimpleNamespace as NS

import httpx
import pytest

from app import providers, rag
from app.config import Settings, settings
from app.providers import Ollama, ProviderUnavailable


def test_local_configuration_remains_available_without_key():
    config = Settings(_env_file=None, generation_provider="ollama", embedding_provider="ollama")
    assert config.generation_provider == config.embedding_provider == "ollama"
    assert config.generation_model == "qwen3:4b"
    assert config.embedding_model == "embeddinggemma" and config.vector_dimensions == 768


def test_native_schema_and_tool_result_translation():
    seen = []

    def server(request):
        body = json.loads(request.content)
        seen.append(body)
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": '{"status":"insufficient","passage_ids":[]}'},
            },
        )

    client = Ollama(httpx.MockTransport(server))
    response = client.responses.create(
        model="qwen3:4b",
        instructions="test",
        input=[
            {
                "type": "function_call",
                "name": "get_tickets",
                "call_id": "c",
                "arguments": '{"limit":1}',
            },
            {"type": "function_call_output", "call_id": "c", "output": "[]"},
        ],
        text={"format": {"schema": {"type": "object"}}},
        tools=[],
    )
    assert response.status == "completed"
    assert seen[0]["format"] == {"type": "object"} and seen[0]["think"] is None
    assert seen[0]["messages"][-1] == {"role": "tool", "tool_name": "get_tickets", "content": "[]"}


def test_streaming_native_tool_call():
    data = [
        {"message": {"content": "Preparando "}, "done": False},
        {
            "message": {
                "tool_calls": [{"function": {"name": "create_ticket", "arguments": {"title": "T"}}}]
            },
            "done": False,
        },
        {"message": {"content": ""}, "done": True, "done_reason": "stop", "eval_count": 3},
    ]
    client = Ollama(
        httpx.MockTransport(
            lambda req: httpx.Response(200, text="\n".join(json.dumps(d) for d in data))
        )
    )
    with client.responses.create(model="qwen3:4b", input=[], stream=True) as stream:
        events = list(stream)
    assert events[0].delta == "Preparando "
    result = events[-1].response
    assert result.output[0].name == "create_ticket" and json.loads(result.output[0].arguments) == {
        "title": "T"
    }
    assert result.usage.output_tokens == 3


@pytest.mark.parametrize(
    "data",
    [
        [{"message": {"content": "partial"}, "done": False}],
        [{"error": "private-server-detail"}],
    ],
)
def test_broken_stream_fails_closed(data):
    client = Ollama(
        httpx.MockTransport(
            lambda req: httpx.Response(200, text="\n".join(json.dumps(d) for d in data))
        )
    )
    with (
        pytest.raises(ProviderUnavailable),
        client.responses.create(model="qwen3:4b", input=[], stream=True) as stream,
    ):
        list(stream)


def test_truncation_is_not_a_completed_answer():
    client = Ollama(
        httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"done": True, "done_reason": "length", "message": {"content": "partial"}}
            )
        )
    )
    assert client.responses.create(model="qwen3:4b", input=[]).status == "incomplete"


def test_provider_errors_do_not_leak_body():
    client = Ollama(
        httpx.MockTransport(lambda req: httpx.Response(500, text="secret document key"))
    )
    with pytest.raises(ProviderUnavailable) as exc:
        client.responses.create(model="qwen3:4b", input=[])
    assert "secret" not in str(exc.value)


def test_embedding_prefix_dimensions_and_identity(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    seen = []

    def server(req):
        if req.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "embeddinggemma:latest", "digest": "digest-v1"}]}
            )
        body = json.loads(req.content)
        seen.append(body)
        return httpx.Response(
            200, json={"embeddings": [[1.0] + [0.0] * 767 for _ in body["input"]]}
        )

    monkeypatch.setattr(rag, "client", Ollama(httpx.MockTransport(server)))
    assert "digest-v1" in rag.embedding_collection()
    assert len(rag.embed_texts(["text"])[0]) == 768
    rag.embed_query("query")
    assert seen[0]["input"] == ["title: none | text: text"]
    assert seen[1]["input"] == ["task: search result | query: query"]
    assert seen[0]["truncate"] is False


@pytest.mark.parametrize("vector", [[0.0] * 1536, [float("nan")] * 1536, [1.0] * 768])
def test_invalid_embedding_vectors_rejected(monkeypatch, vector):
    monkeypatch.setattr(
        rag,
        "client",
        NS(embeddings=NS(create=lambda **kw: NS(data=[NS(index=0, embedding=vector)]))),
    )
    with pytest.raises(RuntimeError):
        rag.embed_texts(["text"])


def test_openai_remains_optional(monkeypatch):
    monkeypatch.setattr(settings, "generation_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(ProviderUnavailable):
        _ = providers.generation_client().responses
    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setattr(providers, "OpenAI", lambda **kw: NS(responses="openai-adapter"))
    assert providers.generation_client().responses == "openai-adapter"


def test_model_digest_change_during_embedding_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    revisions = iter(["before", "after"])
    monkeypatch.setattr(
        rag,
        "client",
        NS(
            digest=lambda _: next(revisions),
            embeddings=NS(
                create=lambda **kw: NS(data=[NS(index=0, embedding=[1.0] + [0.0] * 767)])
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="cambió"):
        rag.embed_texts(["document"])


@pytest.mark.parametrize(
    "failure,fragment",
    [
        (httpx.ConnectError("private connection address"), "conectar"),
        (httpx.ReadTimeout("private request text"), "tiempo"),
    ],
)
def test_local_transport_failures_are_bounded_and_sanitized(failure, fragment):
    def server(request):
        assert request.extensions["timeout"]["connect"] == 5
        assert request.extensions["timeout"]["read"] == settings.ollama_timeout_seconds
        raise failure

    with pytest.raises(ProviderUnavailable, match=fragment) as exc:
        Ollama(httpx.MockTransport(server)).create(model="qwen3:4b", input=[])
    assert "private" not in str(exc.value)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"done": True},
        {"message": []},
        {"message": {"content": 42}},
        {"message": {"tool_calls": [{"function": {"name": "x", "arguments": "{}"}}]}},
        {
            "message": {
                "tool_calls": [{"function": {"name": "x", "arguments": {"n": float("inf")}}}]
            }
        },
    ],
)
def test_local_malformed_responses_fail_closed(data):
    # allow_nan=True here intentionally simulates a malformed upstream JSON body.
    client = Ollama(httpx.MockTransport(lambda r: httpx.Response(200, text=json.dumps(data))))
    with pytest.raises(ProviderUnavailable):
        client.create(model="qwen3:4b", input=[])


def test_local_missing_model_has_actionable_error_without_downloading():
    requests = []

    def server(request):
        requests.append(request.url.path)
        return httpx.Response(404, text="private path/model name")

    with pytest.raises(ProviderUnavailable, match="no se descargó"):
        Ollama(httpx.MockTransport(server)).create(model="absent", input=[])
    assert requests == ["/api/chat"]


def test_local_early_stream_exit_closes_transport_without_consuming_rest():
    class Frames(httpx.SyncByteStream):
        consumed = 0
        closed = False

        def __iter__(self):
            self.consumed += 1
            yield b'{"message":{"content":"Hola"},"done":false}\n'
            self.consumed += 1
            yield b'{"message":{"content":" mundo"},"done":true}\n'

        def close(self):
            self.closed = True

    frames = Frames()
    client = Ollama(httpx.MockTransport(lambda r: httpx.Response(200, stream=frames)))
    with client.create(model="qwen3:4b", input=[], stream=True) as events:
        assert next(events).delta == "Hola"
    assert frames.closed and frames.consumed == 1


def test_local_context_is_configured_and_models_unload(monkeypatch):
    monkeypatch.setattr(settings, "ollama_num_ctx", 4096)
    payload = Ollama().payload({"model": "qwen3:4b", "input": []})
    assert payload["options"]["num_ctx"] == 4096
    assert payload["keep_alive"] == 0 and payload["think"] is None
    assert "temperature" not in payload["options"] and payload["options"]["seed"] == 42


def test_local_thinking_is_not_exposed_in_completed_or_streamed_text():
    frame = {"message": {"thinking": "private-reasoning", "content": "Hola"}, "done": True}
    client = Ollama(httpx.MockTransport(lambda r: httpx.Response(200, json=frame)))
    result = client.create(model="qwen3:4b", input=[])
    assert result.output_text == "Hola" and "private" not in str(vars(result))
    frames = [
        {"message": {"thinking": "private-reasoning"}, "done": False},
        frame,
    ]
    client = Ollama(
        httpx.MockTransport(
            lambda r: httpx.Response(200, text="\n".join(json.dumps(f) for f in frames))
        )
    )
    with client.create(model="qwen3:4b", input=[], stream=True) as stream:
        events = list(stream)
    assert [e.delta for e in events if e.type == "response.output_text.delta"] == ["Hola"]
    assert events[-1].response.output_text == "Hola"


@pytest.mark.parametrize("message", [None, [], "invalid"])
def test_local_stream_rejects_non_object_messages(message):
    client = Ollama(
        httpx.MockTransport(
            lambda r: httpx.Response(200, text=json.dumps({"message": message, "done": True}))
        )
    )
    with (
        pytest.raises(ProviderUnavailable, match="streaming Ollama incompatible"),
        client.create(model="qwen3:4b", input=[], stream=True) as events,
    ):
        list(events)
