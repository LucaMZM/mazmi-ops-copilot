"""Safe runtime configuration shared by the authenticated UI and tests."""

from pathlib import Path

from .config import settings


def configuration():
    def provider(name, model):
        configured = (
            bool(settings.gemini_api_key if name == "gemini" else settings.openai_api_key)
            if name != "ollama"
            else True
        )
        return {
            "provider": "demo" if settings.demo_mode else name,
            "model": model,
            "state": "demo"
            if settings.demo_mode
            else "configured"
            if configured
            else "not_configured",
            "verification": "simulated" if settings.demo_mode else "not_checked",
        }

    from .rag import embedding_collection

    # No network requests from a settings read, including Ollama tags.
    collection = (
        None
        if settings.embedding_provider == "ollama" and not settings.demo_mode
        else embedding_collection()
    )
    return {
        "demo": settings.demo_mode,
        "generation": provider(settings.generation_provider, settings.generation_model),
        "embeddings": {
            **provider(settings.embedding_provider, settings.embedding_model),
            "dimensions": settings.vector_dimensions,
            "collection": collection,
        },
        "voice": {
            "stt": "faster-whisper",
            "stt_configured": bool(
                settings.stt_model_path and Path(settings.stt_model_path).is_dir()
            ),
            "tts": settings.tts_provider,
            "tts_configured": bool(settings.openai_api_key)
            if settings.tts_provider == "openai"
            else bool(settings.piper_model_path and Path(settings.piper_model_path).is_file()),
            "verification": "not_checked",
        },
        "indexing": {
            "max_file_mb": 20,
            "formats": ["pdf", "docx", "txt", "md"],
            "strategy": "hybrid_rrf",
            "top_k": 6,
        },
    }
