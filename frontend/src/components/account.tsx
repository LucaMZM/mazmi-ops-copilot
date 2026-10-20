"use client";
import { FormEvent, useEffect, useState } from "react";
import { Copilot } from "./copilot";

export type Account = {
  email: string;
  workspace_id: string;
  workspaces: { id: string; name: string }[];
};
export function AccountGate() {
  const [account, setAccount] = useState<Account | null>(null);
  const [checking, setChecking] = useState(true);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    const r = await fetch("/api/auth/me");
    if (!r.ok) throw new Error("Sesión no disponible");
    setAccount(await r.json());
  }
  useEffect(() => {
    let active = true;
    fetch("/api/auth/me")
      .then(async (r) => {
        if (r.ok) {
          const a = await r.json();
          if (active) setAccount(a);
        } else if (r.status !== 401)
          throw new Error("El servidor no está disponible");
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const data = {
        email: form.get("email"),
        password: form.get("password"),
        ...(register ? { workspace_name: form.get("workspace") } : {}),
      };
      const r = await fetch(`/api/auth/${register ? "register" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await r.json();
      if (!r.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Revisa los campos. Contraseña mínima: 12 caracteres.",
        );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar sesión");
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    const r = await fetch("/api/auth/logout", { method: "POST" });
    if (!r.ok) throw new Error("No se pudo cerrar sesión");
    setAccount(null);
  }
  async function selectWorkspace(id: string) {
    const r = await fetch("/api/auth/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: id }),
    });
    if (!r.ok) throw new Error("No se pudo cambiar de workspace");
    await load();
  }
  if (checking)
    return (
      <main className="authLoading">
        <p>Conectando con MAZMI…</p>
      </main>
    );
  if (account)
    return (
      <Copilot
        key={account.workspace_id}
        account={account}
        onSignOut={signOut}
        onWorkspace={selectWorkspace}
      />
    );
  return (
    <main className="authScreen">
      <section className="authStory">
        <span className="wordmark">MAZMI SYSTEMS / OPS COPILOT</span>
        <div>
          <h2>
            El conocimiento
            <br />
            tiene consecuencias.
            <br />
            Tú decides cuáles.
          </h2>
          <p>
            Un espacio de trabajo para consultar evidencia, preparar acciones y
            conservar el contexto de cada decisión.
          </p>
        </div>
        <small>CONOCIMIENTO · CRITERIO · CONTROL</small>
      </section>
      <div className="authFormWrap">
        <form className="authPanel" onSubmit={submit}>
          <small>MAZMI / OPS COPILOT</small>
          <h1>
            {register
              ? "Crea tu espacio de trabajo"
              : "Tu conocimiento. Tus decisiones."}
          </h1>
          <p>Documentos, respuestas con fuentes y acciones bajo tu control.</p>
          {error && (
            <div role="alert" className="errorBanner">
              {error}
            </div>
          )}
          <label>
            Email
            <input
              name="email"
              type="email"
              required
              autoComplete="username"
              maxLength={254}
            />
          </label>
          <label>
            Contraseña
            <input
              name="password"
              type="password"
              minLength={12}
              maxLength={128}
              required
              autoComplete={register ? "new-password" : "current-password"}
            />
          </label>
          {register && (
            <label>
              Workspace
              <input
                name="workspace"
                required
                maxLength={100}
                placeholder="Tu empresa o equipo"
              />
            </label>
          )}
          <button disabled={busy} className="primary">
            {busy ? "Conectando…" : register ? "Crear cuenta" : "Entrar"}
          </button>
          <button
            type="button"
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register ? "Ya tengo cuenta" : "Crear cuenta y workspace"}
          </button>
        </form>
      </div>
    </main>
  );
}
