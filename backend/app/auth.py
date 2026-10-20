"""Opaque server-side sessions; workspace always comes from validated membership."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, StringConstraints, field_validator

from .config import settings
from .db import get_conn
from .schemas import StrictModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "mazmi_session"


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    email: str


class Credentials(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=12, max_length=128
    )

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        import re

        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email no válido")
        return value.lower()


class Registration(Credentials):
    workspace_name: str = Field(min_length=1, max_length=100)


class WorkspaceChoice(StrictModel):
    workspace_id: UUID


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + digest


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def principal(request: Request) -> Principal:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Inicia sesión para continuar")
    with get_conn() as conn:
        row = conn.execute(
            """SELECT u.id,s.workspace_id,u.email FROM sessions s
            JOIN users u ON u.id=s.user_id
            JOIN workspace_members m ON m.user_id=u.id AND m.workspace_id=s.workspace_id
            WHERE s.token_hash=%s AND s.expires_at>now()""",
            (token_hash(token),),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Sesión expirada; vuelve a iniciar sesión")
    return Principal(str(row[0]), str(row[1]), row[2])


CurrentUser = Annotated[Principal, Depends(principal)]


def create_session(conn, response: Response, user_id, workspace_id):
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    conn.execute(
        "INSERT INTO sessions(token_hash,user_id,workspace_id) VALUES (%s,%s,%s)",
        (token_hash(token), user_id, workspace_id),
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=86400,
        path="/",
    )


@router.post("/register", status_code=201)
def register(payload: Registration, response: Response):
    with get_conn() as conn:
        # Unique constraint is also checked for concurrent registrations.
        row = conn.execute(
            "INSERT INTO users(email,password_hash) VALUES (%s,%s) ON CONFLICT(email) DO NOTHING RETURNING id",
            (payload.email, password_hash(payload.password)),
        ).fetchone()
        if not row:
            raise HTTPException(409, "No se pudo registrar esa cuenta")
        workspace = conn.execute(
            "INSERT INTO workspaces(name,slug) VALUES (%s,%s) RETURNING id",
            (payload.workspace_name, secrets.token_hex(16)),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO workspace_members(user_id,workspace_id) VALUES (%s,%s)",
            (row[0], workspace),
        )
        create_session(conn, response, row[0], workspace)
    return {"email": payload.email, "workspace_id": str(workspace)}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response):
    # Persistent per-account throttling works across API workers; no password logged.
    with get_conn() as conn:
        key = hashlib.sha256(payload.email.encode()).hexdigest()
        attempts = conn.execute(
            """INSERT INTO login_attempts(key,attempts,window_start) VALUES (%s,1,now())
          ON CONFLICT(key) DO UPDATE SET
          attempts=CASE WHEN login_attempts.window_start<now()-interval '15 minutes' THEN 1 ELSE login_attempts.attempts+1 END,
          window_start=CASE WHEN login_attempts.window_start<now()-interval '15 minutes' THEN now() ELSE login_attempts.window_start END RETURNING attempts""",
            (key,),
        ).fetchone()[0]
    if attempts > 15:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos.")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id,password_hash FROM users WHERE email=%s", (payload.email,)
        ).fetchone()
        stored = row[1] if row else "00" * 16 + ":" + "00" * 64
        if not hmac.compare_digest(password_hash(payload.password, stored.split(":")[0]), stored):
            raise HTTPException(401, "Credenciales incorrectas")
        workspace = conn.execute(
            "SELECT m.workspace_id FROM workspace_members m JOIN workspaces w ON w.id=m.workspace_id WHERE m.user_id=%s ORDER BY w.created_at,m.workspace_id LIMIT 1",
            (row[0],),
        ).fetchone()[0]
        conn.execute("DELETE FROM login_attempts WHERE key=%s", (key,))
        create_session(conn, response, row[0], workspace)
    return {"email": payload.email, "workspace_id": str(workspace)}


@router.post("/logout")
def logout(request: Request, response: Response):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash=%s",
            (token_hash(request.cookies.get(COOKIE, "")),),
        )
    response.delete_cookie(COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT w.id,w.name FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id WHERE m.user_id=%s ORDER BY w.name",
            (user.user_id,),
        ).fetchall()
    return {
        "email": user.email,
        "workspace_id": user.workspace_id,
        "workspaces": [{"id": str(r[0]), "name": r[1]} for r in rows],
    }


@router.post("/workspace")
def select_workspace(payload: WorkspaceChoice, request: Request, user: CurrentUser):
    with get_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM workspace_members WHERE user_id=%s AND workspace_id=%s",
            (user.user_id, payload.workspace_id),
        ).fetchone():
            raise HTTPException(404, "Workspace no encontrado")
        conn.execute(
            "UPDATE sessions SET workspace_id=%s WHERE token_hash=%s",
            (payload.workspace_id, token_hash(request.cookies[COOKIE])),
        )
    return {"workspace_id": str(payload.workspace_id)}


@router.post("/workspaces", status_code=201)
def create_workspace(payload: WorkspaceCreate, user: CurrentUser):
    with get_conn() as conn:
        workspace = conn.execute(
            "INSERT INTO workspaces(name,slug) VALUES (%s,%s) RETURNING id",
            (payload.name, secrets.token_hex(16)),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO workspace_members(user_id,workspace_id) VALUES (%s,%s)",
            (user.user_id, workspace),
        )
    return {"id": str(workspace), "name": payload.name}
