"""Unit tests for the SSE bridge: terminal events, deadline and disconnect handling."""

import asyncio
import json
import time
from threading import Event

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.streaming import GENERIC_ERROR, StreamCancelled, sse_response


def events_of(text):
    return [
        json.loads(line[6:])
        for frame in text.split("\n\n")
        for line in frame.split("\n")
        if line.startswith("data: ")
    ]


def app_for(work, timeout=5.0):
    app = FastAPI()

    @app.post("/s")
    async def endpoint(request: Request):
        return sse_response(request, work, timeout=timeout)

    return app


def test_done_is_terminal_and_status_events_are_forwarded():
    def work(emit, cancelled):
        emit({"type": "status", "text": "uno"})
        emit({"type": "delta", "text": "hola"})
        return {"answer": "hola"}

    response = TestClient(app_for(work)).post("/s")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [e["type"] for e in events_of(response.text)] == ["status", "delta", "done"]


def test_unexpected_exception_yields_one_sanitized_error():
    def work(emit, cancelled):
        raise KeyError("secret private passage")

    response = TestClient(app_for(work)).post("/s")
    events = events_of(response.text)
    assert events == [{"type": "error", "message": GENERIC_ERROR, "status": 500}]
    assert "secret" not in response.text


def test_deadline_sends_timeout_error_and_cancels_late_work():
    observed = {}
    finished = Event()

    def work(emit, cancelled):
        time.sleep(0.6)
        observed["cancelled"] = cancelled.is_set()
        try:
            emit({"type": "delta", "text": "late"})
        except StreamCancelled:
            observed["emit_refused"] = True
        finished.set()
        return {"answer": "late"}

    response = TestClient(app_for(work, timeout=0.2)).post("/s")
    events = events_of(response.text)
    assert events[-1]["type"] == "error" and events[-1]["status"] == 504
    assert finished.wait(3)
    assert observed == {"cancelled": True, "emit_refused": True}


def test_client_disconnect_sets_cancellation_flag():
    started, release, seen = Event(), Event(), {}

    def work(emit, cancelled):
        started.set()
        release.wait(3)
        seen["cancelled"] = cancelled.wait(3)
        return {}

    app = app_for(work)

    async def drive():
        messages = []
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": b"", "more_body": False}
            # Wait until the worker is running, then hang up.
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 3)
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/s",
            "raw_path": b"/s",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        return messages

    asyncio.run(drive())
    release.set()
    time.sleep(0.1)
    assert seen.get("cancelled") is True
