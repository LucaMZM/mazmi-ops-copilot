"""Load the fictional "Aurelia Logística" corpus into a NEW, clearly named workspace.

Explicit and opt-in, for presentations only: it is never run by the application, it logs in
through the public HTTP API like any person would, creates its own workspace and uploads the
ten fictional documents of ``evals/realistic/corpus``. Other workspaces and their data are
never read or modified. The password is asked interactively and never printed or stored.

    cd backend
    python -m app.presentation_corpus --api http://127.0.0.1:8000 --email tu@correo.example
"""

import argparse
import getpass
import sys
from pathlib import Path

import httpx

CORPUS = Path(__file__).resolve().parents[1] / "evals" / "realistic" / "corpus"
WORKSPACE = "Aurelia Logística (ficticio)"
MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def load(api: str, email: str, password: str, origin: str, transport=None) -> dict:
    files = sorted(p for p in CORPUS.iterdir() if p.suffix in MIME)
    with httpx.Client(
        base_url=api, headers={"Origin": origin}, timeout=300, transport=transport
    ) as client:
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            raise SystemExit("No se pudo iniciar sesión con esa cuenta.")
        workspace = client.post("/api/auth/workspaces", json={"name": WORKSPACE})
        workspace.raise_for_status()
        workspace_id = workspace.json()["id"]
        client.post("/api/auth/workspace", json={"workspace_id": workspace_id}).raise_for_status()
        ready = []
        for path in files:
            response = client.post(
                "/api/documents",
                files={"file": (path.name, path.read_bytes(), MIME[path.suffix])},
            )
            ok = response.status_code == 200 and response.json().get("status") == "ready"
            ready.append(ok)
            print(f"{'listo ' if ok else 'ERROR '} {path.name}")
        client.post("/api/auth/logout")
    return {"workspace": WORKSPACE, "documents": len(files), "ready": sum(ready)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="URL del backend")
    parser.add_argument("--email", required=True, help="Cuenta ya registrada en MAZMI")
    parser.add_argument(
        "--origin",
        default="http://127.0.0.1:3000",
        help="Origen permitido por el backend (CORS_ORIGINS)",
    )
    args = parser.parse_args()
    password = getpass.getpass("Contraseña de MAZMI (no se muestra ni se guarda): ")
    result = load(args.api, args.email, password, args.origin)
    print(f"Workspace «{result['workspace']}»: {result['ready']}/{result['documents']} listos.")
    sys.exit(0 if result["ready"] == result["documents"] else 1)


if __name__ == "__main__":
    main()
