"use client";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { ActionCard, Badge, EmptyState } from "../product-ui";
import type { PendingAction } from "../product-types";
import { date } from "@/lib/format";

const TABS = [
  ["PENDING", "Pendientes"],
  ["EXECUTED", "Ejecutadas"],
  ["REJECTED", "Rechazadas"],
  ["ALL", "Todas"],
] as const;

export function ApprovalsView({
  actions,
  busy,
  onDecide,
  onConversation,
}: {
  actions: PendingAction[];
  busy: boolean;
  onDecide: (a: PendingAction, yes: boolean) => void;
  onConversation: (id: string) => void;
}) {
  const [filter, setFilter] = useState<string>("PENDING");
  const filtered = actions.filter((a) => filter === "ALL" || a.status === filter);
  const count = (status: string) => actions.filter((a) => a.status === status).length;
  return (
    <div className="pageSection">
      <header className="pageIntro">
        <div>
          <h2>Tú autorizas, el sistema registra</h2>
          <p>
            Cada propuesta muestra exactamente qué se creará. Solo puedes resolver tus propias
            propuestas de este workspace, y cada decisión queda en Actividad.
          </p>
        </div>
      </header>
      <div className="tabBar" role="group" aria-label="Filtrar aprobaciones">
        {TABS.map(([value, label]) => (
          <button
            key={value}
            aria-pressed={filter === value}
            className={filter === value ? "active" : ""}
            onClick={() => setFilter(value)}
          >
            {label}
            {value !== "ALL" && <span className="tabCount">{count(value)}</span>}
          </button>
        ))}
      </div>
      <div className="approvalList">
        {filtered.map((a) => (
          <div key={a.id} className="approvalEntry">
            {a.status === "PENDING" ? (
              <ActionCard action={a} busy={busy} onDecide={onDecide} />
            ) : (
              <article className="resolvedAction surface">
                <Badge state={a.status === "EXECUTED" ? "ready" : "neutral"}>
                  {a.status === "EXECUTED" ? "Ejecutada tras aprobación" : "Rechazada, sin ejecución"}
                </Badge>
                <h3>{a.payload.title}</h3>
                <p>{a.payload.description}</p>
                {a.resolved_at && (
                  <small>
                    Resuelta el <time dateTime={a.resolved_at}>{date(a.resolved_at)}</time>
                  </small>
                )}
              </article>
            )}
            {a.conversation_id && (
              <button className="textButton" onClick={() => onConversation(a.conversation_id!)}>
                Abrir conversación de origen
              </button>
            )}
          </div>
        ))}
      </div>
      {!filtered.length && (
        <EmptyState title="No hay propuestas en este estado" icon={<ShieldCheck size={22} />}>
          Pide explícitamente una acción en modo DO, por ejemplo «Crea un ticket para revisar el
          acceso». La ejecución siempre requiere tu confirmación.
        </EmptyState>
      )}
    </div>
  );
}
