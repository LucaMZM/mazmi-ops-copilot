"""Explicit smoke test for installed Ollama models: python -m app.check_local.
Never pulls models, executes tool proposals, or alters the database.
"""

import json

from . import rag
from .config import settings
from .evidence import EvidenceDecision
from .providers import generation_client


def main():
    if settings.generation_provider != "ollama" or settings.embedding_provider != "ollama":
        raise RuntimeError("This smoke check only permits Ollama providers")
    client = generation_client()
    result = client.responses.create(
        model=settings.generation_model,
        instructions="Return status sufficient and passage_ids [1].",
        input=[{"role": "user", "content": "Return the requested JSON."}],
        tools=[],
        text={"format": {"schema": EvidenceDecision.model_json_schema()}},
        max_output_tokens=500,
    )
    assert result.status == "completed"
    EvidenceDecision.model_validate_json(result.output_text, strict=True)
    with client.responses.create(
        model=settings.generation_model, input=[{"role": "user", "content": "Say OK."}], stream=True
    ) as stream:
        events = list(stream)
    assert events[-1].type == "response.completed"
    result = client.responses.create(
        model=settings.generation_model,
        input=[{"role": "user", "content": "Call local_probe with value 1."}],
        tools=[
            {
                "name": "local_probe",
                "description": "Test only; never executed",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            }
        ],
    )
    assert len(result.output) == 1 and result.output[0].name == "local_probe"
    assert json.loads(result.output[0].arguments) == {"value": 1}
    vector = rag.embed_query("Prueba de recuperación")
    print(
        json.dumps(
            {
                "structured_output": "passed",
                "stream": "passed",
                "tool_proposal": "passed-not-executed",
                "dimensions": len(vector),
                "collection": rag.embedding_collection(),
            }
        )
    )


if __name__ == "__main__":
    main()
