import json
from types import SimpleNamespace as NS

import httpx
import pytest

from app import rag
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
    assert seen[0]["format"] == {"type": "object"} and seen[0]["think"] is None  # reasoning on
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


def test_embedding_prefix_dimensions_and_identity(monkeypatch, real_revision):
    monkeypatch.setattr(settings, "embedding_dimensions", 768)
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


def test_model_digest_change_during_embedding_is_rejected(monkeypatch, real_revision):
    monkeypatch.setattr(settings, "embedding_dimensions", 768)
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
    assert payload["keep_alive"] == settings.ollama_keep_alive == "5m"
    assert payload["think"] is None  # reasoning "on" is the model's own behaviour
    assert "temperature" not in payload["options"] and payload["options"]["seed"] == 42
    assert Ollama().payload({"model": "qwen3:4b", "input": [], "seed": 43})["options"]["seed"] == 43
    monkeypatch.setattr(settings, "ollama_keep_alive", "0")
    assert Ollama().payload({"model": "qwen3:4b", "input": []})["keep_alive"] == "0"


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


def test_native_metrics_are_allowlisted_and_reject_invalid_values():
    data = {
        "done": True,
        "done_reason": "length",
        "prompt_eval_count": 530,
        "eval_count": 2000,
        "load_duration": 12,
        "eval_duration": 24,
        "total_duration": -1,
        "prompt_eval_duration": True,
        "private_detail": "secret",
        "message": {"thinking": "private-thought", "content": ""},
    }
    result = Ollama().result(data)
    assert result.provider_metrics == {
        "prompt_eval_count": 530,
        "eval_count": 2000,
        "load_duration": 12,
        "eval_duration": 24,
        "done_reason": "length",
        "content_chars": 0,
        "thinking_chars": len("private-thought"),
    }
    assert "private" not in str(vars(result)) and "secret" not in str(vars(result))
    data["done_reason"] = "private-arbitrary-message"
    assert Ollama().result(data).provider_metrics["done_reason"] == "unknown"


def test_streamed_thinking_metrics_count_lengths_without_emitting_text():
    frames = [
        {"message": {"thinking": "secret"}, "done": False},
        {"message": {"thinking": "thought", "content": "{}"}, "done": True, "done_reason": "stop"},
    ]
    client = Ollama(
        httpx.MockTransport(
            lambda r: httpx.Response(200, text="\n".join(json.dumps(f) for f in frames))
        )
    )
    with client.create(model="qwen3:4b", input=[], stream=True) as stream:
        events = list(stream)
    assert events[-1].response.provider_metrics["thinking_chars"] == 13
    assert events[-1].response.provider_metrics["content_chars"] == 2
    assert "secret" not in str(events) and "thought" not in str(events)


def test_reasoning_off_disables_thinking_and_is_never_greedy(monkeypatch):
    kwargs = {
        "model": "qwen3:4b",
        "instructions": "Evalúa.",
        "input": [{"role": "user", "content": "x"}],
        "text": {"format": {"schema": {"type": "object"}}},
    }
    default = Ollama().payload(kwargs)
    assert default["think"] is None and "temperature" not in default["options"]
    monkeypatch.setattr(settings, "ollama_reasoning", "off")
    payload = Ollama().payload(kwargs)
    assert payload["think"] is False
    assert payload["messages"][0]["content"].endswith("/no_think")
    assert payload["options"]["temperature"] == 0.7 and payload["options"]["top_k"] == 20
    assert payload["format"] == {"type": "object"} and payload["options"]["seed"] == 42


def test_warm_up_loads_both_models_with_the_configured_keep_alive():
    seen = []

    def server(req):
        seen.append((req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={})

    assert Ollama(httpx.MockTransport(server)).warm_up() == ["qwen3:4b", "embeddinggemma"]
    assert [path for path, _ in seen] == ["/api/generate", "/api/embed"]
    assert all(body["keep_alive"] == settings.ollama_keep_alive for _, body in seen)
    assert "prompt" not in seen[0][1]  # load-only: nothing is generated


def test_warm_up_never_raises_when_ollama_is_down_or_a_model_is_missing():
    def down(req):
        raise httpx.ConnectError("private address")

    assert Ollama(httpx.MockTransport(down)).warm_up() == []

    def missing_chat_model(req):
        return httpx.Response(404 if req.url.path == "/api/generate" else 200, json={})

    assert Ollama(httpx.MockTransport(missing_chat_model)).warm_up() == ["embeddinggemma"]
