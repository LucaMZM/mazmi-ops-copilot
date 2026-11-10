import pytest

from app import rag
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_local_settings(monkeypatch):
    """Normal tests use mocks and never reach Ollama, a paid provider or a model download.

    Mock vectors are 1536 wide, so dimensions are pinned here; tests that exercise the real
    EmbeddingGemma width or digest lookup override these explicitly. The default evidence
    mode keeps the historical passage-ID contract that the integration mocks speak; the
    quote-verified mode has its own dedicated tests.
    """
    monkeypatch.setattr(settings, "embedding_dimensions", 1536)
    monkeypatch.setattr(settings, "evidence_mode", "passage_ids_v5")
    monkeypatch.setattr(settings, "chat_max_concurrent", 2)
    monkeypatch.setattr(settings, "ollama_warmup", False)
    monkeypatch.setattr(settings, "ollama_reasoning", "on")
    monkeypatch.setattr(rag, "embedding_revision", lambda: "test-digest")


@pytest.fixture
def real_revision(monkeypatch):
    """Use the adapter's own digest lookup (mocked transport) instead of the test digest."""
    monkeypatch.setattr(
        rag, "embedding_revision", lambda: rag.client.digest(settings.embedding_model)
    )
