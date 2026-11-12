"use client";
import { FormEvent, useEffect, useState } from "react";
import { Layers, Quote, ShieldCheck } from "lucide-react";
import { Copilot } from "./copilot";
import { Spinner } from "./product-ui";
import { applyTheme } from "@/hooks/use-theme";
import { RobotMark } from "./brand/robot-mark";

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
    applyTheme();
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
        <div className="backdropScene" aria-hidden="true" />
        <p role="status">
          <Spinner /> Conectando con MAZMI…
        </p>
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
      <div className="backdropScene" aria-hidden="true" />
      <section className="authStory">
        <div className="brand">
          <span className="brandTile large" aria-hidden="true">
            <RobotMark size={26} className="blinking" />
          </span>
          <div>
            <b>MAZMI</b>
            <small>Ops Copilot</small>
          </div>
        </div>
        <h2>El conocimiento de tu equipo, con pruebas y bajo tu control.</h2>
        <p>
          Pregunta a vuestros documentos y verifica cada cita. Prepara acciones operativas que
          solo se ejecutan cuando una persona las confirma.
        </p>
        <ul className="authPrinciples">
          <li>
            <Quote size={18} aria-hidden="true" />
            <span>
              <strong>Respuestas citadas.</strong> Frases literales de tus documentos o una
              abstención explícita, nunca datos inventados.
            </span>
          </li>
          <li>
            <ShieldCheck size={18} aria-hidden="true" />
            <span>
              <strong>Aprobación humana.</strong> Cada acción es una propuesta hasta que la
              confirmas, y queda registrada.
            </span>
          </li>
          <li>
            <Layers size={18} aria-hidden="true" />
            <span>
              <strong>Espacios aislados.</strong> Documentos, conversaciones y decisiones
              separados por workspace.
            </span>
          </li>
        </ul>
      </section>
      <form className="authPanel glass" onSubmit={submit}>
        <h1>{register ? "Crea tu espacio de trabajo" : "Inicia sesión"}</h1>
        <p>
          {register
            ? "La contraseña necesita al menos 12 caracteres."
            : "Accede a los documentos y decisiones de tus workspaces."}
        </p>
        {error && (
          <div role="alert" className="errorBanner">
            {error}
          </div>
        )}
        <label>
          Email
          <input name="email" type="email" required autoComplete="username" maxLength={254} />
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
            <input name="workspace" required maxLength={100} placeholder="Tu empresa o equipo" />
          </label>
        )}
        <button disabled={busy} className="primary">
          {busy ? "Conectando…" : register ? "Crear cuenta" : "Entrar"}
        </button>
        <button
          type="button"
          className="textButton"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register ? "Ya tengo cuenta" : "Crear cuenta y workspace"}
        </button>
      </form>
    </main>
  );
}
