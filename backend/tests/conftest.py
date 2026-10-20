import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def legacy_test_provider(monkeypatch):
    # Existing suites deliberately exercise the preserved OpenAI contract with mocks.
    # Local provider tests override these fields explicitly; never reach either vendor.
    monkeypatch.setattr(settings, "generation_provider", "openai")
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "tts_provider", "openai")
    monkeypatch.setattr(settings, "embedding_dimensions", None)
