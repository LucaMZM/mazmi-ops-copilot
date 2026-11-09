"use client";
import { FileText, MessageSquareText, ShieldCheck, Upload } from "lucide-react";
import { DocBadge } from "./knowledge-view";
import type { Activity, Conversation, DocumentItem, PendingAction, SystemInfo, View } from "../product-types";
import { compatible, date, eventNames, plural } from "@/lib/format";

export function WorkspaceView({
  name,
  docs,
  actions,
  activity,
  conversations,
  system,
  onView,
  onPrompt,
  onUpload,
  onConversation,
}: {
  name: string;
  docs: DocumentItem[];
  actions: PendingAction[];
  activity: Activity[];
  conversations: Conversation[];
  system: SystemInfo | null;
  onView: (v: View) => void;
  onPrompt: (text: string) => void;
  onUpload: () => void;
  onConversation: (id: string) => void;
}) {
  const pending = actions.filter((a) => a.status === "PENDING");
  const available = docs.filter((d) => d.status === "ready" && compatible(d, system) !== false);
  const attention = docs.filter((d) => d.status === "failed" || compatible(d, system) === false);
  return (
    <div className="workspacePage">
      <section className="workspaceHero surface">
        <div className="heroText">
          <h2>{name}</h2>
          <p>
            Lo que este equipo sabe y lo que tiene pendiente de decidir. Cada respuesta cita sus
            fuentes y cada acción espera tu confirmación.
          </p>
          <div className="heroActions">
            <button className="primary" onClick={() => onView("Copilot")}>
              <MessageSquareText size={17} aria-hidden="true" /> Abrir una consulta
            </button>
            <button className="ghost" onClick={onUpload}>
              <Upload size={16} aria-hidden="true" /> Subir documento
            </button>
          </div>
        </div>
        <dl className="heroFacts">
          <div>
            <dt>Documentos listos</dt>
            <dd>{available.length}</dd>
          </div>
          <div>
            <dt>Por decidir</dt>
            <dd>{pending.length}</dd>
          </div>
          <div>
            <dt>Conversaciones</dt>
            <dd>{conversations.length}</dd>
          </div>
        </dl>
      </section>

      <div className="workspaceGrid">
        <section className="surface panel">
          <div className="sectionHeading">
            <h3>Conocimiento disponible</h3>
            <button className="textButton" onClick={() => onView("Knowledge")}>
              Ver biblioteca
            </button>
          </div>
          {available.length ? (
            <ul className="plainList">
              {available.slice(0, 4).map((d) => (
                <li key={d.id}>
                  <button className="documentLink" onClick={() => onView("Knowledge")}>
                    <FileText size={19} aria-hidden="true" />
                    <span>
                      <strong>{d.filename}</strong>
                      <small>
                        {plural(d.chunks, "fragmento", "fragmentos")}, {d.embedding_model}
                      </small>
                    </span>
                    <DocBadge doc={d} system={system} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              Aún no hay documentos compatibles listos. Sube una política o un procedimiento para
              empezar.
            </p>
          )}
          {attention.length > 0 && (
            <p className="attentionNote">
              {plural(attention.length, "documento necesita", "documentos necesitan")} revisión
              (indexación fallida o colección incompatible).
            </p>
          )}
          <div className="suggestedPrompts">
            <h4>Para empezar</h4>
            {["¿Cuántos días de vacaciones hay?", "¿Qué información hay sobre el acceso?"].map(
              (q) => (
                <button key={q} onClick={() => onPrompt(q)}>
                  {q}
                </button>
              ),
            )}
          </div>
        </section>

        <section className={`surface panel attentionSection ${pending.length ? "hasPending" : ""}`}>
          <ShieldCheck size={22} aria-hidden="true" />
          <h3>
            {pending.length
              ? `${plural(pending.length, "propuesta", "propuestas")} por revisar`
              : "Decisiones al día"}
          </h3>
          <p>
            {pending.length
              ? "Ninguna propuesta se ejecuta hasta que la apruebas. Revisa su alcance antes de decidir."
              : "Las acciones que pidas en modo DO aparecerán aquí para tu aprobación."}
          </p>
          <button className={pending.length ? "primary amber" : "ghost"} onClick={() => onView("Approvals")}>
            Revisar aprobaciones
          </button>
        </section>
      </div>

      <div className="workspaceGrid">
        <section className="surface panel">
          <div className="sectionHeading">
            <h3>Conversaciones recientes</h3>
          </div>
          {conversations.length ? (
            <ul className="plainList">
              {conversations.slice(0, 4).map((c) => (
                <li key={c.id}>
                  <button className="conversationRow" onClick={() => onConversation(c.id)}>
                    <span>{c.title}</span>
                    {c.updated_at && <time dateTime={c.updated_at}>{date(c.updated_at)}</time>}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Tus consultas quedarán guardadas aquí.</p>
          )}
        </section>
        <section className="surface panel">
          <div className="sectionHeading">
            <h3>Actividad reciente</h3>
            <button className="textButton" onClick={() => onView("Activity")}>
              Abrir registro
            </button>
          </div>
          {activity.length ? (
            <ol className="activityLines">
              {activity.slice(0, 5).map((a) => (
                <li key={a.id}>
                  <span className={`eventDot ${a.type.includes("executed") ? "success" : a.type.includes("failed") ? "failed" : ""}`} />
                  <strong>{eventNames[a.type] ?? "Evento del workspace"}</strong>
                  <time dateTime={a.created_at}>{date(a.created_at)}</time>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">La actividad aparecerá al subir documentos o iniciar consultas.</p>
          )}
        </section>
      </div>
    </div>
  );
}
