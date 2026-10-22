"""Safe runtime configuration shared by the authenticated UI and tests."""

import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

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

    check = _recent_check()
    from .rag import embedding_collection

    # No network requests from a settings read, including Ollama tags.
    collection = (
        (check.get("collection") if check and check["status"] == "passed" else None)
        if settings.embedding_provider == "ollama" and not settings.demo_mode
        else embedding_collection()
    )
    result = {
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

    if check:
        result["local_check"] = {k: v for k, v in check.items() if k != "collection"}
        for field in ("generation", "embeddings"):
            result[field]["verification"] = "passed" if check["status"] == "passed" else "failed"
            result[field]["checked_at"] = check["checked_at"]
    return result


# Last completed local fixture probe, scoped to this process and exact configuration.
# GET /api/system never performs network I/O; timestamps are historical, not a
# continuous liveness guarantee. Restart/config changes/expiry require rechecking.
_check_lock = Lock()
_last_check = None
CHECK_TTL_SECONDS = 300


class LocalCheckBusy(RuntimeError):
    pass


def _signature():
    return (
        settings.demo_mode,
        settings.generation_provider,
        settings.embedding_provider,
        settings.ollama_base_url,
        settings.generation_model,
        settings.embedding_model,
        settings.vector_dimensions,
        settings.embedding_revision,
        settings.ollama_num_ctx,
    )


def _recent_check():
    check = _last_check
    if check and check[0] == _signature() and time.monotonic() - check[1] < CHECK_TTL_SECONDS:
        return check[2]
    return None


def verify_local():
    global _last_check
    if (
        settings.demo_mode
        or settings.generation_provider != "ollama"
        or settings.embedding_provider != "ollama"
    ):
        raise ValueError("Selecciona el perfil Ollama real para realizar esta prueba local.")
    if not _check_lock.acquire(blocking=False):
        raise LocalCheckBusy("Ya hay una prueba local en curso.")
    signature = _signature()
    try:
        from .check_local import run_checks

        report = run_checks(full=False)
        report["checked_at"] = datetime.now(timezone.utc).isoformat()
        # Do not publish full model inventory/digests or arbitrary probe errors to UI.
        safe = {
            "status": report["status"],
            "checked_at": report["checked_at"],
            "scope": "structured-output-and-embedding-fixtures",
            "duration_ms": report.get("duration_ms"),
            "message": "Prueba local completada con texto ficticio."
            if report["status"] == "passed"
            else "Ollama no completó la prueba. Comprueba el servicio, los modelos y sus dimensiones.",
            "collection": report.get("checks", {}).get("embeddings", {}).get("collection"),
        }
        if signature == _signature():
            _last_check = (signature, time.monotonic(), safe)
        return safe
    finally:
        _check_lock.release()
