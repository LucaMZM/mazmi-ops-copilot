"""Bounded native-format diagnostic on two public, fixed-passage cases.

Explicit --live only. No retrieval, downloads, cloud fallback or production switch.
Never records prompts, document bodies, final answer text or reasoning text.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import settings
from .evidence import documentary_answer
from .providers import Ollama

CASES = ("known_purchase_limit", "multipart_purchase_approval_audit")


class FormatOffDiagnostic(Ollama):
    """Change only native grammar enforcement and make its output contract textual."""

    def payload(self, kwargs):
        payload = super().payload(kwargs)
        if not kwargs.get("text"):
            return payload
        payload.pop("format", None)
        payload["messages"][0]["content"] += (
            '\nDevuelve solo un objeto JSON con "status" ("sufficient", '
            '"insufficient" o "conflicting") y "passage_ids" (lista de IDs enteros).'
        )
        return payload


def diagnose(client, output_path):
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "evals/local_cases.json").read_text()
    )
    questions = {q["name"]: q for q in fixture["questions"]}
    documents = {d["filename"]: d["text"] for d in fixture["documents"]}
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "provenance": "New execution; public fixture passages only",
        "mode": "diagnostic-native-format-off-fixed-passages",
        "model": settings.generation_model,
        "retrieval": "Not measured; only expected public fixture documents supplied",
        "changes": "Native format removed; equivalent JSON contract appended as plain text",
        "limits": {
            "max_calls": 2,
            "max_output_tokens_per_call": 2000,
            "timeout_seconds": settings.ollama_timeout_seconds,
            "num_ctx": settings.ollama_num_ctx,
            "think": None,
            "seed": 42,
            "keep_alive": 0,
        },
        "cases": [],
        "limitation": "Diagnostic only; not a paired RAG comparison or a release acceptance result",
    }
    for name in CASES:
        case = questions[name]
        sources = [{"content": documents[f]} for f in case["expected_documents"]]
        start = time.perf_counter()
        try:
            _, _, meta = documentary_answer(client, case["question"], sources)
            result = {
                "name": name,
                "expected_abstention": False,
                "abstained": bool(meta["abstention_reason"]),
                "reason": meta["abstention_reason"],
                "model_assessment_performed": meta["model_assessment_performed"],
                "selected_passage_ids": meta["selected_passage_ids"],
                "provider_metrics": meta.get("provider_metrics", {}),
            }
        except (RuntimeError, ValueError, TypeError) as exc:
            # Safe class name only: upstream exceptions can carry private bodies.
            result = {
                "name": name,
                "expected_abstention": False,
                "provider_error": type(exc).__name__,
            }
        result["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        report["cases"].append(result)
        report["attempted_cases"] = len(report["cases"])
        report["answered_cases"] = sum(r.get("abstained") is False for r in report["cases"])
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.live:
        parser.error("Requires --live")
    report = diagnose(FormatOffDiagnostic(), args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
