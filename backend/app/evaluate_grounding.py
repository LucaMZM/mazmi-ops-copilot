"""Offline paired answer-policy evaluation with explicit, untrusted assessor doubles.

Does not measure LLM semantic accuracy: mock_semantic_verdict cases only test wiring.
The adversarial known_semantic_gap deliberately exposes remaining false sufficiency.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

from .evidence import documentary_answer


def evaluate():
    cases = json.loads(
        (Path(__file__).resolve().parents[1] / "evals/grounding_cases.json").read_text()
    )
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
        text, _, meta = documentary_answer(
            NS(responses=NS(create=create)), case["question"], sources
        )
        abstained = bool(meta["abstention_reason"])
        # Frozen previous gate: nonempty retrieval + valid [1] permits an assertion.
        refs = [int(n) for n in re.findall(r"\[(\d+)\]", case["baseline_answer"])]
        before_abstained = not sources or not refs or any(n < 1 or n > len(sources) for n in refs)
        results.append(
            {
                "name": case["name"],
                "check": case["check"],
                "expected_abstention": case["expected_abstention"],
                "before_correct": before_abstained == case["expected_abstention"],
                "after_correct": abstained == case["expected_abstention"],
                "abstained": abstained,
                "reason": meta["abstention_reason"],
                "answer": text,
            }
        )
    negatives = [r for r in results if r["expected_abstention"]]
    positives = [r for r in results if not r["expected_abstention"]]
    return {
        "mode": "offline-assessor-doubles",
        "cases": results,
        "before_correct_abstentions": sum(r["before_correct"] for r in negatives),
        "after_correct_abstentions": sum(r["after_correct"] for r in negatives),
        "unanswerable_cases": len(negatives),
        "false_abstentions": sum(r["abstained"] for r in positives),
        "answerable_cases": len(positives),
        "limitation": "Semantic verdicts are mocked. Known semantic gap is retained, not hidden. Exact passages prevent new prose, not all wrong applicability decisions.",
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
