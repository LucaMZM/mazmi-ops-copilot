"""Server-Sent Events bridge between a synchronous worker and an async response.

Design notes (see VALIDATION.md, "Streaming"):

* The worker runs in its own thread because provider SDKs and psycopg calls are
  blocking. Events cross to the event loop through ``call_soon_threadsafe``; the
  response coroutine awaits them instead of polling a queue.
* A turn produces a handful of small events (status, one delta, done/error), so the
  queue does not need a size bound; a slow client only delays its own socket.
* Disconnects and the global deadline set ``cancelled``. ``emit`` then raises
  ``StreamCancelled`` at the next checkpoint and the persistence step refuses to
  commit. A provider request already in flight is *not* interrupted: its result is
  discarded when it returns. We never claim otherwise.
* Every exit path sends exactly one terminal event (``done`` or ``error``) unless the
  client is gone. Unexpected exceptions are logged by type only and reported with a
  generic message, so provider bodies or document text never reach the browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from threading import Event, Thread

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15.0
GENERIC_ERROR = "No se pudo completar la respuesta"
TIMEOUT_ERROR = (
    "La respuesta superó el tiempo máximo. No se guardó nada de esta consulta; "
    "revisa el historial antes de repetir una acción."
)


class StreamCancelled(RuntimeError):
    """The client disconnected or the deadline passed; nothing must be persisted."""


def frame(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"


def sse_response(
    request: Request,
    work: Callable[[Callable[[dict], None], Event], dict],
    *,
    timeout: float,
    cancelled_exc: type[BaseException] = StreamCancelled,
    initial: list[dict] | None = None,
) -> StreamingResponse:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    cancelled = Event()

    def put(item: dict | None) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # Event loop already closed: the client is gone.
            cancelled.set()

    def emit(event: dict) -> None:
        if cancelled.is_set():
            raise cancelled_exc("Cliente desconectado o tiempo agotado")
        put(event)

    def worker() -> None:
        try:
            result = work(emit, cancelled)
            if not cancelled.is_set():
                put({"type": "done", "data": result})
        except cancelled_exc:
            pass
        except HTTPException as exc:
            put({"type": "error", "message": str(exc.detail), "status": exc.status_code})
        except Exception as exc:  # noqa: BLE001 - terminal event must always be sent
            logger.error("Stream worker failed: %s", type(exc).__name__)
            put({"type": "error", "message": GENERIC_ERROR, "status": 500})
        finally:
            put(None)

    Thread(target=worker, daemon=True, name="mazmi-stream").start()

    async def stream():
        deadline = loop.time() + timeout
        try:
            # Flush headers immediately so proxies and the browser see progress.
            yield ": stream-open\n\n"
            for event in initial or []:
                yield frame(event)
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    cancelled.set()
                    yield frame({"type": "error", "message": TIMEOUT_ERROR, "status": 504})
                    return
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=min(HEARTBEAT_SECONDS, remaining)
                    )
                except TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": keep-alive\n\n"
                    continue
                if item is None:
                    return
                yield frame(item)
        finally:
            # Disconnect, timeout or normal end: later emits become no-ops/cancellations.
            cancelled.set()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
