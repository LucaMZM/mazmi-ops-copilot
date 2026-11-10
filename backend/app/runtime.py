"""Safe runtime configuration shared by the authenticated UI and tests."""

import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from .config import settings


def configuration():
    """Configured local models. No network I/O: a settings read never contacts Ollama."""

    def model(name):
        return {"provider": "ollama", "model": name, "verification": "not_checked"}

    check = _recent_check()
    result = {
        "generation": model(settings.generation_model),
        "embeddings": {
            **model(settings.embedding_model),
            "dimensions": settings.vector_dimensions,
            "collection": check.get("collection")
            if check and check["status"] == "passed"
            else None,
        },
        "runtime": {
            "local_endpoint": urlparse(settings.ollama_base_url).hostname
            in {"127.0.0.1", "localhost", "::1", "host.docker.internal"},
            "reasoning": settings.ollama_reasoning,
            "context_tokens": settings.ollama_num_ctx,
            "timeout_seconds": settings.ollama_timeout_seconds,
            "keep_alive": settings.ollama_keep_alive,
            "max_concurrent_turns": settings.chat_max_concurrent,
            "evidence_mode": settings.evidence_mode,
        },
        "voice": {
            "stt": "faster-whisper",
            "stt_configured": bool(
                settings.stt_model_path and Path(settings.stt_model_path).is_dir()
            ),
            "tts": "piper",
            "tts_configured": bool(
                settings.piper_model_path and Path(settings.piper_model_path).is_file()
            ),
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
        settings.ollama_base_url,
        settings.generation_model,
        settings.embedding_model,
        settings.vector_dimensions,
        settings.ollama_num_ctx,
        settings.ollama_reasoning,
        settings.evidence_mode,
    )


def _recent_check():
    check = _last_check
    if check and check[0] == _signature() and time.monotonic() - check[1] < CHECK_TTL_SECONDS:
        return check[2]
    return None


def verify_local():
    global _last_check
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
