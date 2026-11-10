"""Local Ollama adapter for the application's Responses-shaped contract.

Uses Ollama's native HTTP API. No downloads, cloud providers, fallbacks, automatic
execution of tools or private-body logs.
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace as NS
from uuid import uuid4

import httpx

from .config import settings


class ProviderUnavailable(RuntimeError):
    pass


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
                timeout=httpx.Timeout(settings.ollama_timeout_seconds, connect=5, write=30, pool=5),
                transport=self.transport,
                trust_env=False,
            ) as client:
                yield client
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(
                "Ollama agotó el tiempo de espera; no se cambió de proveedor."
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                "No se puede conectar con Ollama. Inicia el servicio local."
            ) from exc
        except httpx.HTTPStatusError as exc:
            message = (
                "Modelo no instalado en Ollama; no se descargó automáticamente."
                if exc.response.status_code == 404
                else "Ollama rechazó la petición; comprueba modelos, contexto y memoria disponible."
            )
            raise ProviderUnavailable(message) from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderUnavailable(
                "Ollama no disponible o respuesta incompatible. Comprueba servicio y modelos instalados."
            ) from exc

    def warm_up(self):
        """Load the chat and embedding models and keep them resident. Returns what loaded.

        Uses Ollama's documented load-only calls (an empty /api/generate request and a tiny
        /api/embed). Never raises: an unavailable server simply means no warm-up.
        """
        loaded = []
        for path, body in (
            (
                "/api/generate",
                {"model": settings.generation_model, "keep_alive": settings.ollama_keep_alive},
            ),
            (
                "/api/embed",
                {
                    "model": settings.embedding_model,
                    "input": "calentamiento",
                    "keep_alive": settings.ollama_keep_alive,
                },
            ),
        ):
            try:
                with self.http() as client:
                    client.post(path, json=body).raise_for_status()
                loaded.append(body["model"])
            except (ProviderUnavailable, httpx.HTTPError):
                continue
        return loaded

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
                    "keep_alive": settings.ollama_keep_alive,
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
            # "on": let Ollama separate reasoning with the model default. Never forward
            # message.thinking to application text.
            "think": None,
            "stream": bool(kwargs.get("stream")),
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                # Preserve model sampling defaults: Qwen3 explicitly warns that
                # greedy decoding can cause endless reasoning repetitions.
                "seed": kwargs.get("seed", 42),
                "num_ctx": settings.ollama_num_ctx,
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
        if settings.ollama_reasoning == "off":
            # Measured default (VALIDATION.md): with reasoning on, Qwen3 4B spent its whole
            # output budget thinking (timeouts, empty answers). Disable the reasoning phase
            # with Qwen3's documented soft switch and its recommended non-thinking sampling
            # (temperature 0.7, top_p 0.8, top_k 20). Never greedy decoding.
            payload["think"] = False
            messages[0]["content"] = (messages[0]["content"] + "\n/no_think").strip()
            payload["options"].update({"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0})
        return payload

    def result(self, data, content=None, calls=None, thinking_chars=None):
        if not isinstance(data, dict):
            raise ProviderUnavailable("Respuesta Ollama incompatible")
        if "error" in data:
            raise ProviderUnavailable(
                "Ollama devolvió un error; no se ejecutó ninguna herramienta."
            )
        message = data.get("message")
        if not isinstance(message, dict):
            raise ProviderUnavailable("Respuesta Ollama sin mensaje válido")
        text = message.get("content", "") if content is None else content
        tool_calls = calls if calls is not None else message.get("tool_calls", [])
        if (
            not isinstance(text, str)
            or len(text) > 100000
            or not isinstance(tool_calls, list)
            or len(tool_calls) > 4
        ):
            raise ProviderUnavailable("Respuesta Ollama incompatible o demasiado grande")
        output = []
        for item in tool_calls:
            fn = item["function"]
            if (
                not isinstance(fn["arguments"], dict)
                or not isinstance(fn["name"], str)
                or not fn["name"]
            ):
                raise ProviderUnavailable("Argumentos de herramienta Ollama incompatibles")
            output.append(
                NS(
                    type="function_call",
                    name=fn["name"],
                    arguments=json.dumps(fn["arguments"], allow_nan=False),
                    call_id=uuid4().hex,
                )
            )
        metrics = {
            key: data[key]
            for key in (
                "prompt_eval_count",
                "eval_count",
                "total_duration",
                "load_duration",
                "prompt_eval_duration",
                "eval_duration",
            )
            if type(data.get(key)) is int and 0 <= data[key] <= 2**63 - 1
        }
        metrics["done_reason"] = (
            data.get("done_reason") if data.get("done_reason") in {"stop", "length"} else "unknown"
        )
        metrics["content_chars"] = len(text)
        metrics["thinking_chars"] = (
            thinking_chars
            if thinking_chars is not None
            else len(message["thinking"])
            if isinstance(message.get("thinking"), str)
            else 0
        )
        return NS(
            provider_metrics=metrics,
            status="completed"
            if data.get("done") and data.get("done_reason", "stop") == "stop"
            else "incomplete",
            output=output,
            output_text=text,
            usage=NS(
                input_tokens=metrics.get("prompt_eval_count", 0),
                output_tokens=metrics.get("eval_count", 0),
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
                content, calls, thinking_chars = "", [], 0
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ProviderUnavailable("Evento de streaming Ollama incompatible")
                    if "error" in data:
                        raise ProviderUnavailable("Error durante streaming Ollama")
                    message = data.get("message", {})
                    if not isinstance(message, dict):
                        raise ProviderUnavailable("Mensaje de streaming Ollama incompatible")
                    delta = message.get("content", "")
                    new_calls = message.get("tool_calls", [])
                    if not isinstance(delta, str) or not isinstance(new_calls, list):
                        raise ProviderUnavailable("Evento de streaming Ollama incompatible")
                    thought = message.get("thinking", "")
                    if isinstance(thought, str):
                        thinking_chars += len(thought)
                    content += delta
                    calls.extend(new_calls)
                    if len(content) > 100000 or len(calls) > 4:
                        raise ProviderUnavailable("Respuesta Ollama demasiado grande")
                    if delta:
                        yield NS(type="response.output_text.delta", delta=delta)
                    if data.get("done"):
                        result = self.result(data, content, calls, thinking_chars)
                        yield NS(
                            type="response.completed"
                            if result.status == "completed"
                            else "response.incomplete",
                            response=result,
                        )
                        return
                raise ProviderUnavailable("Stream Ollama interrumpido")

            yield events()


def generation_client():
    return Ollama()


def embeddings_client():
    return Ollama()
