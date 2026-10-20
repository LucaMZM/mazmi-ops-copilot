"""Gemini Developer API adapter. No automatic tools, retries, billing or fallback."""

import json
from contextlib import contextmanager
from types import SimpleNamespace as NS
from uuid import uuid4

import httpx
from google import genai
from google.genai import errors, types

from .config import settings
from .providers import ProviderQuotaExceeded, ProviderUnavailable, require_config


class Gemini:
    def __init__(self, transport=None):
        self.transport = transport
        self.responses = self
        self.embeddings = NS(create=self.embed)

    @contextmanager
    def connection(self):
        require_config("gemini")
        try:
            with genai.Client(
                api_key=settings.gemini_api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    timeout=120000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                    client_args={"transport": self.transport, "trust_env": False},
                ),
            ) as client:
                yield client
        except errors.APIError as exc:
            if exc.code == 429:
                raise ProviderQuotaExceeded(
                    "Cuota Gemini agotada (429). Espera o revisa la cuota gratuita en AI Studio; no se cambió de proveedor."
                ) from None
            raise ProviderUnavailable(
                "Gemini no pudo completar la solicitud. Comprueba clave, modelo y disponibilidad en AI Studio."
            ) from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ProviderUnavailable(
                "Respuesta Gemini inválida o conexión interrumpida."
            ) from None

    def payload(self, kwargs):
        contents, calls, seen = [], {}, set()
        for raw in kwargs.get("input", []):
            item = raw if isinstance(raw, dict) else vars(raw)
            if item.get("type") == "function_call":
                # Keep original Content, including thought signatures, only in this request.
                original = item.get("gemini_content")
                if original is None:
                    raise ValueError("Missing original Gemini function content")
                calls[item["call_id"]] = (item["name"], item.get("gemini_call_id"))
                if id(original) not in seen:
                    contents.append(original)
                    seen.add(id(original))
            elif item.get("type") == "function_call_output":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    id=calls[item["call_id"]][1],
                                    name=calls[item["call_id"]][0],
                                    response={"result": json.loads(item["output"])},
                                )
                            )
                        ],
                    )
                )
            else:
                contents.append(
                    types.Content(
                        role="model" if item["role"] == "assistant" else "user",
                        parts=[types.Part(text=item["content"])],
                    )
                )
        config = types.GenerateContentConfig(
            system_instruction=kwargs.get("instructions"),
            max_output_tokens=kwargs.get("max_output_tokens", 2000),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if kwargs.get("tools"):
            config.tools = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"],
                            description=t["description"],
                            parameters_json_schema=t["parameters"],
                        )
                        for t in kwargs["tools"]
                    ]
                )
            ]
        if kwargs.get("text"):
            config.response_mime_type = "application/json"
            config.response_json_schema = kwargs["text"]["format"]["schema"]
        return {"model": kwargs["model"], "contents": contents, "config": config}

    def result(self, response, parts=None):
        candidates = response.candidates or []
        candidate = candidates[0] if len(candidates) == 1 else None
        original = (
            types.Content(role="model", parts=parts)
            if parts is not None
            else (candidate.content if candidate else None)
        )
        output, text = [], ""
        for part in (original.parts or []) if original else []:
            if part.thought:
                continue
            if part.text:
                text += part.text
            if part.function_call:
                fn = part.function_call
                if not isinstance(fn.args, dict):
                    raise ValueError("Invalid function arguments")
                output.append(
                    NS(
                        type="function_call",
                        name=fn.name,
                        arguments=json.dumps(fn.args),
                        call_id=fn.id or uuid4().hex,
                        gemini_content=original,
                        gemini_call_id=fn.id,
                    )
                )
        usage = response.usage_metadata
        return NS(
            status="completed" if candidate and candidate.finish_reason == "STOP" else "incomplete",
            output=output,
            output_text=text,
            usage=NS(
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            ),
        )

    def create(self, **kwargs):
        payload = self.payload(kwargs)
        if kwargs.get("stream"):
            return self.stream(payload)
        with self.connection() as client:
            return self.result(client.models.generate_content(**payload))

    @contextmanager
    def stream(self, payload):
        with self.connection() as client:
            stream = client.models.generate_content_stream(**payload)

            def events():
                parts, last, size = [], None, 0
                for chunk in stream:
                    last = chunk
                    if len(chunk.candidates or []) != 1:
                        raise ValueError("Missing candidate")
                    candidate = chunk.candidates[0]
                    for part in (candidate.content.parts or []) if candidate.content else []:
                        parts.append(part)
                        if part.text and not part.thought:
                            size += len(part.text)
                            if size > 100000:
                                raise ValueError("Output limit")
                            yield NS(type="response.output_text.delta", delta=part.text)
                    if candidate.finish_reason:
                        result = self.result(chunk, parts)
                        yield NS(
                            type="response.completed"
                            if result.status == "completed"
                            else "response.incomplete",
                            response=result,
                        )
                        return
                if last is None or not last.candidates[0].finish_reason:
                    raise ProviderUnavailable("Stream Gemini interrumpido; respuesta descartada.")

            try:
                yield events()
            finally:
                stream.close()

    def embed(self, *, model, input, dimensions):
        if model != "gemini-embedding-2":
            raise ProviderUnavailable(
                "Modelo de embeddings Gemini no soportado por este adaptador."
            )
        if any(len(text.encode("utf-8")) > 8000 for text in input):
            raise ProviderUnavailable(
                "Entrada demasiado larga para embeddings Gemini (máximo 8000 bytes)."
            )
        with self.connection() as client:
            # Each Content is a distinct embedding, not one aggregated multi-part vector.
            response = client.models.embed_content(
                model=model,
                contents=[types.Content(parts=[types.Part(text=text)]) for text in input],
                config=types.EmbedContentConfig(output_dimensionality=dimensions),
            )
            return NS(
                data=[
                    NS(index=i, embedding=e.values) for i, e in enumerate(response.embeddings or [])
                ]
            )
