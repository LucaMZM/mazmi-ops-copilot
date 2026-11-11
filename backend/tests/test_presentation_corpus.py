import json

import httpx
import pytest

from app import presentation_corpus


def test_loader_creates_its_own_workspace_and_only_uploads_the_fictional_corpus():
    calls = []

    def server(request):
        calls.append((request.method, request.url.path))
        assert request.headers["origin"] == "http://127.0.0.1:3000"
        if request.url.path == "/api/auth/workspaces":
            assert json.loads(request.content) == {"name": "Aurelia Logística (ficticio)"}
            return httpx.Response(201, json={"id": "new-workspace"})
        if request.url.path == "/api/auth/workspace":
            assert json.loads(request.content) == {"workspace_id": "new-workspace"}
        if request.url.path == "/api/documents":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json={})

    result = presentation_corpus.load(
        "http://api.test",
        "ana@example.com",
        "secreto",
        "http://127.0.0.1:3000",
        transport=httpx.MockTransport(server),
    )
    assert result == {"workspace": "Aurelia Logística (ficticio)", "documents": 10, "ready": 10}
    methods = {method for method, _ in calls}
    assert methods == {"POST"}  # never reads, deletes or changes anything else
    paths = [path for _, path in calls]
    assert paths[:3] == ["/api/auth/login", "/api/auth/workspaces", "/api/auth/workspace"]
    assert paths.count("/api/documents") == 10 and paths[-1] == "/api/auth/logout"


def test_loader_stops_without_creating_anything_when_login_fails():
    calls = []

    def server(request):
        calls.append(request.url.path)
        return httpx.Response(401, json={"detail": "x"})

    with pytest.raises(SystemExit):
        presentation_corpus.load(
            "http://api.test",
            "ana@example.com",
            "mal",
            "http://127.0.0.1:3000",
            transport=httpx.MockTransport(server),
        )
    assert calls == ["/api/auth/login"]
