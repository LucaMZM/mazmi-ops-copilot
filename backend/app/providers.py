"""Small adapters for the existing Responses-shaped application contract.

Ollama uses its native HTTP API, not assumed OpenAI Responses compatibility.
No downloads, cloud fallback, automatic execution of tools or private-body logs.
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace as NS
from uuid import uuid4

import httpx
from openai import OpenAI

from .config import settings


class ProviderUnavailable(RuntimeError):
    pass


class ProviderQuotaExceeded(ProviderUnavailable):
    pass


def require_config(provider):
    if settings.demo_mode:
        settings.guard_demo()
        return
    if provider == "gemini" and not settings.gemini_api_key:
        raise ProviderUnavailable(
            "Gemini seleccionado: configura GEMINI_API_KEY solo en el servidor."
        )
    if provider == "openai" and not settings.openai_api_key:
        raise ProviderUnavailable("OpenAI seleccionado: configura OPENAI_API_KEY o usa Ollama.")


def openai_client():
    require_config("openai")
    return OpenAI(api_key=settings.openai_api_key, timeout=120, max_retries=0)


class Ollama:
    def __init__(self, transport=None):
        self.transport = transport
        self.responses = self
        self.embeddings = NS(create=self.embed)

    @contextmanager
    def http(self):
        try:
            with httpx.Client(
                base_url=settings.ollama_base_url,
                timeout=120,
                transport=self.transport,
                trust_env=False,
            ) as client:
                yield client
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderUnavailable(
                "Ollama no disponible o respuesta incompatible. Comprueba servicio y modelos instalados."
            ) from exc

    def digest(self, model):
        with self.http() as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            for item in response.json()["models"]:
                if item["name"] in {model, model + ":latest"}:
                    digest = item.get("digest")
                    if isinstance(digest, str) and digest:
                        return digest
        raise ProviderUnavailable(
            "Modelo de embeddings no instalado en Ollama. Instálalo explícitamente cuando haya espacio."
        )

    def embed(self, *, model, input, dimensions):
        with self.http() as client:
            response = client.post(
                "/api/embed",
                json={
                    "model": model,
                    "input": input,
                    "dimensions": dimensions,
                    "truncate": False,
                    "keep_alive": 0,
                },
            )
            response.raise_for_status()
            values = response.json()["embeddings"]
            return NS(data=[NS(index=i, embedding=v) for i, v in enumerate(values)])

    def payload(self, kwargs):
        messages = [{"role": "system", "content": kwargs.get("instructions", "")}]
        names = {}
        for raw in kwargs.get("input", []):
            item = raw if isinstance(raw, dict) else vars(raw)
            if item.get("type") == "function_call":
                names[item["call_id"]] = item["name"]
                messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": item["name"],
                                    "arguments": json.loads(item["arguments"]),
                                }
                            }
                        ],
                    }
                )
            elif item.get("type") == "function_call_output":
                if item["call_id"] not in names:
                    raise RuntimeError("Tool result without matching call")
                messages.append(
                    {"role": "tool", "tool_name": names[item["call_id"]], "content": item["output"]}
                )
            else:
                messages.append({"role": item["role"], "content": item["content"]})
        payload = {
            "model": kwargs["model"],
            "messages": messages,
            "think": False,
            "stream": bool(kwargs.get("stream")),
            "keep_alive": 0,
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": kwargs.get("max_output_tokens", 2000),
            },
            "tools": [
                {
                    "type": "function",
                    "function": {k: t[k] for k in ("name", "description", "parameters")},
                }
                for t in kwargs.get("tools", [])
            ],
        }
        if kwargs.get("text"):
            payload["format"] = kwargs["text"]["format"]["schema"]
        return payload

    def result(self, data, content=None, calls=None):
        if "error" in data:
            raise ProviderUnavailable(
                "Ollama devolvió un error; no se ejecutó ninguna herramienta."
            )
        message = data.get("message", {})
        output = []
        for item in calls if calls is not None else message.get("tool_calls", []):
            fn = item["function"]
            if not isinstance(fn["arguments"], dict):
                raise RuntimeError("Malformed tool arguments")
            output.append(
                NS(
                    type="function_call",
                    name=fn["name"],
                    arguments=json.dumps(fn["arguments"]),
                    call_id=uuid4().hex,
                )
            )
        return NS(
            status="completed"
            if data.get("done") and data.get("done_reason", "stop") == "stop"
            else "incomplete",
            output=output,
            output_text=message.get("content", "") if content is None else content,
            usage=NS(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            ),
        )

    def create(self, **kwargs):
        payload = self.payload(kwargs)
        if payload["stream"]:
            return self.stream(payload)
        with self.http() as client:
            response = client.post("/api/chat", json=payload)
            response.raise_for_status()
            return self.result(response.json())

    @contextmanager
    def stream(self, payload):
        with self.http() as client, client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()

            def events():
                content, calls = "", []
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise ProviderUnavailable("Error durante streaming Ollama")
                    message = data.get("message", {})
                    delta = message.get("content", "")
                    content += delta
                    calls.extend(message.get("tool_calls", []))
                    if len(content) > 100000 or len(calls) > 4:
                        raise RuntimeError("Provider output limit exceeded")
                    if delta:
                        yield NS(type="response.output_text.delta", delta=delta)
                    if data.get("done"):
                        result = self.result(data, content, calls)
                        yield NS(
                            type="response.completed"
                            if result.status == "completed"
                            else "response.incomplete",
                            response=result,
                        )
                        return
                raise ProviderUnavailable("Stream Ollama interrumpido")

            yield events()


class OpenAIAdapter:
    @property
    def responses(self):
        return openai_client().responses

    @property
    def embeddings(self):
        return openai_client().embeddings


def generation_client():
    if settings.demo_mode:
        from .demo import DemoProvider

        return DemoProvider()
    if settings.generation_provider == "gemini":
        from .gemini import Gemini

        return Gemini()
    return Ollama() if settings.generation_provider == "ollama" else OpenAIAdapter()


def embeddings_client():
    if settings.demo_mode:
        from .demo import DemoProvider

        return DemoProvider()
    if settings.embedding_provider == "gemini":
        from .gemini import Gemini

        return Gemini()
    return Ollama() if settings.embedding_provider == "ollama" else OpenAIAdapter()
