"""Reproducible evidence-policy evaluation; no network unless --live is explicit.

Default assessor doubles test backend safeguards, not model semantic accuracy.
Live mode is Ollama-only, uses fixed source passages (not retrieval/embeddings),
and records remaining semantic errors and conservative refusals without hiding them.
"""

import argparse
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace as NS

from .evidence import documentary_answer

EVALS = Path(__file__).resolve().parents[1] / "evals"


def evaluate(*, client=None, case_names=None, include_answers=True):
    cases = json.loads((EVALS / "grounding_cases.json").read_text())
    if case_names is not None:
        unknown = set(case_names) - {case["name"] for case in cases}
        if unknown:
            raise ValueError("Unknown evaluation case")
        cases = [case for case in cases if case["name"] in case_names]
    historical = {
        case["name"]: case
        for case in json.loads((EVALS / "product-grounding-results.json").read_text())["after"][
            "cases"
        ]
    }
    results = []
    for case in cases:

        def create(decision=case["decision"], **kwargs):
            assert kwargs["tools"] == []
            assert kwargs["text"]["format"]["strict"] is True
            return NS(status="completed", output=[], output_text=json.dumps(decision), usage=None)

        sources = [
            {"content": text, "filename": f"doc-{i}.txt", "page": i + 1}
            for i, text in enumerate(case["texts"])
        ]
        started = time.perf_counter()
        try:
            text, _, meta = documentary_answer(
                client or NS(responses=NS(create=create)), case["question"], sources
            )
        except Exception as exc:
            if client is None:
                raise
            # Do not include provider bodies, URLs, source documents or credentials.
            results.append(
                {
                    "name": case["name"],
                    "check": case["check"],
                    "expected_abstention": case["expected_abstention"],
                    "provider_error": type(exc).__name__,
                    "model_assessment_performed": True,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
            continue
        abstained = bool(meta["abstention_reason"])
        refs = [int(n) for n in re.findall(r"\[(\d+)\]", case["baseline_answer"])]
        before_abstained = not sources or not refs or any(n < 1 or n > len(sources) for n in refs)
        result = {
            "name": case["name"],
            "check": case["check"],
            "expected_abstention": case["expected_abstention"],
            "before_correct": before_abstained == case["expected_abstention"],
            "after_correct": abstained == case["expected_abstention"],
            "abstained": abstained,
            "reason": meta["abstention_reason"],
            "policy": meta["evidence_policy"],
            "model_assessment_performed": meta["model_assessment_performed"],
            "selected_passage_ids": meta["selected_passage_ids"],
            "citation_ids_valid": all(1 <= i <= len(sources) for i in meta["citations"]),
            "gold_source_selection_correct": not abstained
            and not case["expected_abstention"]
            and set(meta["selected_passage_ids"]) == set(case["decision"]["passage_ids"]),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if include_answers:
            result["answer"] = text
        results.append(result)
    completed = [r for r in results if "provider_error" not in r]
    negatives = [r for r in completed if r["expected_abstention"]]
    positives = [r for r in completed if not r["expected_abstention"]]
    answered = [r for r in completed if not r["abstained"]]
    paired = [r for r in completed if r["name"] in historical]
    paired_negatives = [r for r in paired if r["expected_abstention"]]
    return {
        "mode": "live-ollama-fixed-passages" if client is not None else "offline-assessor-doubles",
        "retrieval": "fixed-fixture-passages; no vector search or embeddings measured",
        "cases": results,
        "provider_errors": len(results) - len(completed),
        "completed_cases": len(completed),
        "assessor_calls": sum(r["model_assessment_performed"] for r in results),
        "before_correct_abstentions": sum(r["before_correct"] for r in negatives),
        "before_description": "Legacy citation-only gate; historical extractive_v2 comparison is separate below",
        "after_correct_abstentions": sum(r["after_correct"] for r in negatives),
        "unanswerable_cases": len(negatives),
        "false_abstentions": sum(r["abstained"] for r in positives),
        "answerable_cases": len(positives),
        "answer_precision": (
            sum(not r["expected_abstention"] for r in answered) / len(answered)
            if answered
            else None
        ),
        "gold_source_selection_correct": sum(r["gold_source_selection_correct"] for r in completed),
        "all_citation_ids_valid": (
            all(r["citation_ids_valid"] for r in completed) if completed else None
        ),
        "historical_extractive_v2_comparison": {
            "evidence": "frozen mocked observations; live results are not a paired model comparison",
            "matching_cases": len(paired),
            "unanswerable_cases": len(paired_negatives),
            "previous_correct_abstentions": sum(
                historical[r["name"]]["after_correct"] for r in paired_negatives
            ),
            "current_correct_abstentions": sum(r["after_correct"] for r in paired_negatives),
            "current_false_abstentions": sum(
                r["abstained"] for r in paired if not r["expected_abstention"]
            ),
        },
        "limitation": (
            "Mock verdicts test backend guards, not model semantics. Live mode tests only the "
            "assessor on fixed passages, not the RAG pipeline. Exact passages and valid citation "
            "IDs do not prove applicability. Known semantic gaps and conservative refusals remain."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicit Ollama-only model calls")
    parser.add_argument("--case", action="append", dest="case_names", help="Run only named cases")
    args = parser.parse_args()
    client = None
    if args.live:
        from .config import settings
        from .providers import generation_client

        if settings.demo_mode or settings.generation_provider != "ollama":
            parser.error("--live requires DEMO_MODE=false and GENERATION_PROVIDER=ollama")
        client = generation_client()
    print(
        json.dumps(
            evaluate(client=client, case_names=args.case_names, include_answers=not args.live),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
