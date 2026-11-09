"use client";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Badge, EmptyState } from "../product-ui";
import type { Activity } from "../product-types";
import { date, eventNames } from "@/lib/format";

const DETAIL_KEYS = [
  "model",
  "retrieved_chunks",
  "retrieval_ms",
  "evidence_policy",
  "abstention_reason",
  "action_id",
  "document_id",
  "chunks",
] as const;

function kind(type: string) {
  if (type.includes("failed")) return "failed";
  if (type.includes("executed")) return "success";
  if (type.startsWith("action.")) return "decision";
  return "neutral";
}

export function ActivityView({ events, onRefresh }: { events: Activity[]; onRefresh: () => void }) {
  const [filter, setFilter] = useState("all");
  const filtered = events.filter((e) => filter === "all" || e.type.startsWith(filter));
  return (
    <div className="pageSection">
      <header className="pageIntro">
        <div>
          <h2>Registro del workspace</h2>
          <p>
            Últimos 50 eventos: quién hizo qué y con qué resultado. Los prompts privados y el
            contenido de los documentos no aparecen aquí.
          </p>
        </div>
        <button className="ghost" onClick={onRefresh}>
          <RefreshCw size={16} aria-hidden="true" /> Actualizar actividad
        </button>
      </header>
      <div className="tableToolbar">
        <select aria-label="Filtrar actividad" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">Toda la actividad</option>
          <option value="action.">Aprobaciones y acciones</option>
          <option value="document.">Documentos</option>
          <option value="chat.">Consultas</option>
          <option value="tool.">Herramientas</option>
          <option value="conversation.">Conversaciones</option>
        </select>
        <span className="toolbarCount">{filtered.length} eventos</span>
      </div>
      <ol className="timeline">
        {filtered.map((a) => (
          <li key={a.id} className={`timelineItem ${kind(a.type)}`}>
            <span className="timelineDot" aria-hidden="true" />
            <div className="timelineCard surface">
              <div className="auditHeading">
                <h3>{eventNames[a.type] ?? a.type}</h3>
                <time dateTime={a.created_at}>{date(a.created_at)}</time>
              </div>
              <p className="muted">
                {a.actor}
                {a.duration_ms != null ? `, ${a.duration_ms} ms` : ""}
              </p>
              <div className="auditFacts">
                {typeof a.details.mode === "string" && <Badge state="neutral">Modo {a.details.mode}</Badge>}
                {typeof a.details.generation_provider === "string" && (
                  <Badge state="neutral">{a.details.generation_provider}</Badge>
                )}
                {a.type === "action.executed" && <Badge state="ready">Confirmación humana verificada</Badge>}
                {a.type === "action.proposed" && <Badge state="incompatible">Sin ejecutar</Badge>}
                {typeof a.details.filename === "string" && <span>{a.details.filename}</span>}
                {typeof a.details.ticket_id === "number" && <span>Ticket #{a.details.ticket_id}</span>}
                {typeof a.details.abstention_reason === "string" && (
                  <span>Abstención: {a.details.abstention_reason}</span>
                )}
              </div>
              <details>
                <summary>Detalles técnicos</summary>
                <dl className="eventDetails">
                  {DETAIL_KEYS.map(
                    (k) =>
                      a.details[k] != null && (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{String(a.details[k])}</dd>
                        </div>
                      ),
                  )}
                </dl>
              </details>
            </div>
          </li>
        ))}
      </ol>
      {!filtered.length && (
        <EmptyState title="Registro sin eventos">
          Prueba otro filtro o inicia una consulta para registrar actividad.
        </EmptyState>
      )}
    </div>
  );
}
