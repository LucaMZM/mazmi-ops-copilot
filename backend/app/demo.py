"""Explicit development-only provider. Uses real persistence, auth and approval paths.
No general intelligence: documented keyword fixtures, no vendor requests.
"""

import hashlib
import json
import re
import secrets
from contextlib import contextmanager
from types import SimpleNamespace as NS

from .config import settings


def vector(text, dimensions):
    values = [0.0] * dimensions
    for word in re.findall(r"[\w-]+", text.lower()):
        index = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % dimensions
        values[index] += 1
    return values


class DemoProvider:
    def __init__(self):
        settings.guard_demo()
        self.responses = self
        self.embeddings = NS(create=self.embed)

    def digest(self, model):
        return "fixture-v1"

    def embed(self, *, model, input, dimensions):
        return NS(
            data=[NS(index=i, embedding=vector(text, dimensions)) for i, text in enumerate(input)]
        )

    def create(self, **kwargs):
        settings.guard_demo()
        if kwargs.get("stream"):
            return self.stream(kwargs)
        tools = kwargs.get("tools", [])
        inputs = kwargs.get("input", [])
        outputs, text = (
            [],
            "Resultado de demostración. Consulta el registro para verificar la operación.",
        )
        if kwargs.get("text"):
            data = json.loads(inputs[-1]["content"])
            question = data["question"].lower()
            topics = [t for t in ("vacaciones", "acceso", "gastos") if t in question]
            ids = [p["id"] for p in data["passages"] if topics and topics[0] in p["text"].lower()]
            unsupported = any(w in question for w in ("salario", "marte", "despido", "contraseña"))
            text = json.dumps(
                {
                    "status": "sufficient" if ids and not unsupported else "insufficient",
                    "passage_ids": ids[:2] if not unsupported else [],
                }
            )
        elif inputs and (
            isinstance(inputs[-1], dict) and inputs[-1].get("type") == "function_call_output"
        ):
            text = "Resultado de la consulta de tickets (demo):\n" + inputs[-1]["output"]
        elif tools:
            tool = tools[0]["name"]
            args = (
                {"limit": 10}
                if tool == "get_tickets"
                else {
                    "title": "Revisar acceso de incorporación",
                    "description": "Solicitud ficticia. Comprobar el acceso al entorno de operaciones antes del alta.",
                    "priority": "MEDIUM",
                }
            )
            outputs = [
                NS(type="function_call", name=tool, arguments=json.dumps(args), call_id="demo-call")
            ]
            text = ""
        return NS(
            status="completed",
            output=outputs,
            output_text=text,
            usage=NS(input_tokens=0, output_tokens=0),
        )

    @contextmanager
    def stream(self, kwargs):
        result = self.create(**{**kwargs, "stream": False})
        yield iter([NS(type="response.completed", response=result)])


def seed():
    """Seed a NEW dedicated demo database via existing HTTP handlers; never reset data."""
    settings.guard_demo()
    import psycopg
    from fastapi.testclient import TestClient

    from .main import app
    from .migrate import migrate

    # Refuse before any migration on a populated database, even if named *_demo.
    with psycopg.connect(settings.database_url) as conn:
        for table in ("users", "documents", "tickets"):
            if (
                conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]
                and conn.execute(
                    f"SELECT 1 FROM {table} LIMIT 1"  # Fixed table names above, never user input.
                ).fetchone()
            ):
                raise RuntimeError(
                    "Demo seed requires an empty database; existing data was preserved"
                )
    migrate()
    password = secrets.token_urlsafe(24)
    with TestClient(app, headers={"Origin": "http://localhost:3000"}) as api:
        r = api.post(
            "/api/auth/register",
            json={
                "email": "demo@mazmi.local",
                "password": password,
                "workspace_name": "MAZMI · Operaciones",
            },
        )
        r.raise_for_status()
        for name, text in {
            "Politica-de-vacaciones.md": "# Vacaciones\nLas vacaciones anuales son 25 días laborables. La solicitud de vacaciones requiere aprobación de la persona responsable con 10 días de antelación.",
            "Protocolo-de-acceso.txt": "El acceso al entorno de operaciones requiere aprobación humana. El acceso se solicita mediante un ticket interno y se registra en auditoría. Nunca compartas contraseñas.",
            "Guia-de-gastos.md": "Los gastos de viaje necesitan justificante y aprobación previa. El límite de gastos por comida es de 25 euros por persona.",
        }.items():
            api.post(
                "/api/documents", files={"file": (name, text.encode(), "text/plain")}
            ).raise_for_status()
        api.post("/api/documents", files={"file": ("Documento-sin-texto.txt", b"", "text/plain")})
        for question, mode in [
            ("¿Cuántos días de vacaciones hay?", "ASK"),
            ("¿Cuál es el salario durante las vacaciones?", "ASK"),
            ("Crea un ticket para revisar acceso", "DO"),
        ]:
            api.post("/api/chat", json={"message": question, "mode": mode}).raise_for_status()
        api.post("/api/auth/workspaces", json={"name": "MAZMI · Laboratorio"}).raise_for_status()
    print(
        f"Demo seeded. Sign in: demo@mazmi.local / {password} "
        "(generated development password; store privately, never publish)"
    )


if __name__ == "__main__":
    seed()
