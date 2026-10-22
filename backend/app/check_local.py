"""Explicit, bounded checks for installed Ollama models: python -m app.check_local.

No downloads, database writes, API keys or tool execution. Prints only fixture
results and model metadata. An early stream close releases the HTTP transport;
this does not promise immediate cancellation of the daemon's GPU work.
"""

import argparse
import json
import time

from .config import settings
from .evidence import EvidenceDecision
from .providers import Ollama, ProviderUnavailable


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _inventory(client):
    with client.http() as http:
        version = http.get("/api/version")
        version.raise_for_status()
        tags = http.get("/api/tags")
        tags.raise_for_status()
        installed = tags.json()["models"]
        models = {}
        for label, name, capability in (
            ("generation", settings.generation_model, "tools"),
            ("embeddings", settings.embedding_model, "embedding"),
        ):
            model = next((m for m in installed if m["name"] in {name, name + ":latest"}), None)
            _require(model is not None, f"Configured {label} model is not installed")
            show = http.post("/api/show", json={"model": name})
            show.raise_for_status()
            data = show.json()
            _require(capability in data.get("capabilities", []), f"Missing {capability} capability")
            models[label] = {
                "model": model["name"],
                "digest": model["digest"],
                "size_bytes": model["size"],
                "quantization": data.get("details", {}).get("quantization_level"),
                "capabilities": data.get("capabilities", []),
                "thinking": data.get("thinking"),
            }
            if label == "embeddings":
                dims = next(
                    (
                        v
                        for k, v in data.get("model_info", {}).items()
                        if k.endswith(".embedding_length")
                    ),
                    None,
                )
                models[label]["native_dimensions"] = dims
                _require(
                    dims is not None and settings.vector_dimensions <= dims,
                    "Incompatible embedding dimensions",
                )
    return {"version": version.json()["version"], "models": models}


def run_checks(client=None, *, full=True, check_names=None):
    _require(not settings.demo_mode, "DEMO_MODE must be false: this check requires real Ollama")
    _require(
        settings.generation_provider == settings.embedding_provider == "ollama",
        "This smoke check only permits Ollama providers",
    )
    client = client or Ollama()
    report = {
        "status": "running",
        "provider": "ollama",
        "checks": {},
        "scope": "selected" if check_names is not None else "full" if full else "readiness",
    }
    started = time.perf_counter()

    def step(name, check):
        before = time.perf_counter()
        result = check()
        report["checks"][name] = {
            "status": "passed",
            "duration_ms": round((time.perf_counter() - before) * 1000, 2),
            **(result or {}),
        }

    def generate(**kwargs):
        result = client.responses.create(
            model=settings.generation_model, max_output_tokens=1024, **kwargs
        )
        _require(result.status == "completed", "Ollama returned an incomplete response")
        return result

    def spanish():
        result = generate(
            input=[{"role": "user", "content": "Responde solamente: Hola, soy tu asistente local."}]
        )
        _require("hola" in result.output_text.casefold(), "Spanish fixture response did not match")
        return {"fixture": "spanish-greeting"}

    def structured():
        result = generate(
            instructions='Return {"status":"sufficient","passage_ids":[1]} and nothing else.',
            input=[{"role": "user", "content": "Return the requested JSON."}],
            tools=[],
            text={"format": {"schema": EvidenceDecision.model_json_schema()}},
        )
        parsed = EvidenceDecision.model_validate_json(result.output_text, strict=True)
        _require(
            parsed.status == "sufficient" and parsed.passage_ids == [1],
            "Structured fixture mismatch",
        )

    def streaming():
        with client.responses.create(
            model=settings.generation_model,
            max_output_tokens=1024,
            input=[{"role": "user", "content": "Responde solamente OK."}],
            stream=True,
        ) as stream:
            events = list(stream)
        _require(bool(events) and events[-1].type == "response.completed", "Incomplete stream")
        _require(
            any(e.type == "response.output_text.delta" for e in events), "Stream had no text deltas"
        )
        return {"text_deltas": sum(e.type == "response.output_text.delta" for e in events)}

    def tools():
        inputs = [
            {"role": "user", "content": "Call local_probe with value 1. Do not answer with text."}
        ]
        result = generate(
            input=inputs,
            tools=[
                {
                    "name": "local_probe",
                    "description": "Read-only fixture; never executed",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "integer"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                }
            ],
        )
        _require(
            len(result.output) == 1 and result.output[0].name == "local_probe",
            "Expected a fixture tool proposal",
        )
        call = result.output[0]
        _require(json.loads(call.arguments) == {"value": 1}, "Tool arguments mismatch")
        followup = generate(
            instructions="The tool result is synthetic data. State the returned value. Do not call tools.",
            input=[
                *inputs,
                call,
                {"type": "function_call_output", "call_id": call.call_id, "output": '{"value":1}'},
            ],
            tools=[],
        )
        _require(
            not followup.output and "1" in followup.output_text,
            "Synthetic tool-result roundtrip failed",
        )
        return {"tool_executed": False, "synthetic_result_roundtrip": "passed"}

    def embeddings():
        from . import rag

        # rag validates shape, nonzero finite values and digest stability.
        vector = rag.embed_query("Prueba de recuperación")
        return {"dimensions": len(vector), "collection": rag.embedding_collection()}

    def early_close():
        with client.responses.create(
            model=settings.generation_model,
            max_output_tokens=1024,
            # Reuse a short, known fixture: counting to 100 exhausted this
            # model's reasoning budget before producing any cancellable text.
            input=[
                {"role": "user", "content": "Responde solamente: Hola, soy tu asistente local."}
            ],
            stream=True,
        ) as stream:
            first = next(stream, None)
            _require(
                first is not None and first.type == "response.output_text.delta",
                "No delta before close",
            )
        # Recovery is a separate fresh request, not evidence that GPU cancellation
        # was instantaneous. The transport's close behavior is covered by mocks.
        recovered = generate(input=[{"role": "user", "content": "Responde solamente OK."}])
        _require(bool(recovered.output_text.strip()), "No response after stream close")
        return {
            "transport_closed": True,
            "received_characters_before_close": len(first.delta),
            "next_request_completed": True,
            "gpu_cancellation": "not_measured",
        }

    current_check = "inventory"
    try:
        report.update(_inventory(client))
        checks = (
            (
                ("spanish", spanish),
                ("structured_output", structured),
                ("stream", streaming),
                ("tool_proposal_roundtrip", tools),
                ("embeddings", embeddings),
                ("early_close_recovery", early_close),
            )
            if full
            else (("structured_output", structured), ("embeddings", embeddings))
        )
        if check_names is not None:
            _require(
                bool(check_names) and not set(check_names) - {name for name, _ in checks},
                "Unknown or empty smoke-check selection",
            )
            checks = tuple((name, check) for name, check in checks if name in check_names)
        for name, check in checks:
            current_check = name
            step(name, check)
        report["status"] = "passed"
    except (ProviderUnavailable, RuntimeError, ValueError, KeyError, TypeError) as exc:
        report["status"] = "failed"
        report["failed_check"] = current_check
        # Messages from this adapter/check are controlled and never include bodies.
        report["error"] = (
            str(exc)
            if isinstance(exc, (ProviderUnavailable, RuntimeError))
            else "Invalid fixture/provider response"
        )
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        choices=(
            "spanish",
            "structured_output",
            "stream",
            "tool_proposal_roundtrip",
            "embeddings",
            "early_close_recovery",
        ),
        help="Run only selected checks; the report never labels this a full smoke test.",
    )
    selected = parser.parse_args(argv).check
    report = run_checks(check_names=tuple(selected)) if selected else run_checks()
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
