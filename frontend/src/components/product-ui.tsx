"use client";
import { memo, useEffect, useRef, type ReactNode } from "react";
import { AlertCircle, Check, FileText, ShieldCheck, X } from "lucide-react";
import type { PendingAction, Source } from "./product-types";

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="emptyState">
      <div className="emptyMark" aria-hidden="true">
        {icon ?? <FileText size={22} />}
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}

export function Badge({ state, children }: { state: string; children: ReactNode }) {
  return <span className={`badge ${state}`}>{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role={label ? "img" : undefined} aria-label={label} />;
}

const priorityLabel: Record<string, string> = {
  LOW: "Baja",
  MEDIUM: "Media",
  HIGH: "Alta",
  URGENT: "Urgente",
};

export function ActionCard({
  action,
  busy,
  onDecide,
}: {
  action: PendingAction;
  busy: boolean;
  onDecide: (a: PendingAction, yes: boolean) => void;
}) {
  return (
    <article className="actionCard" aria-label={`Propuesta: ${action.payload.title}`}>
      <div className="actionHeader">
        <ShieldCheck size={17} aria-hidden="true" />
        <span>Propuesta sin ejecutar</span>
        <Badge state={`priority ${action.payload.priority.toLowerCase()}`}>
          Prioridad {priorityLabel[action.payload.priority] ?? action.payload.priority}
        </Badge>
      </div>
      <h3>{action.payload.title}</h3>
      <p className="actionDescription">{action.payload.description}</p>
      <div className="consequence">
        <strong>Si confirmas</strong>
        <p>
          Se creará un ticket interno en este workspace con este título, descripción y
          prioridad. La decisión queda registrada en Actividad y no se puede deshacer desde
          aquí.
        </p>
      </div>
      <div className="actionButtons">
        <button className="ghost" disabled={busy} onClick={() => onDecide(action, false)}>
          <X size={16} aria-hidden="true" /> Rechazar
        </button>
        <button className="primary amber" disabled={busy} onClick={() => onDecide(action, true)}>
          <Check size={16} aria-hidden="true" /> Confirmar
        </button>
      </div>
    </article>
  );
}

export function Inspector({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    root.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const elements = root.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input, select, textarea, summary, [tabindex="0"]',
        );
        if (!elements?.length) {
          e.preventDefault();
          return;
        }
        const first = elements[0],
          last = elements[elements.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === root.current)) {
          e.preventDefault();
          last.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last || document.activeElement === root.current)
        ) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div className="inspectorBackdrop" onClick={onClose}>
      <div
        ref={root}
        className="inspector glass"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="iconButton" aria-label="Cerrar inspector" onClick={onClose}>
            <X size={20} />
          </button>
        </header>
        <div className="inspectorBody">{children}</div>
      </div>
    </div>
  );
}

export function SourceChip({
  source,
  index,
  selected,
  onOpen,
}: {
  source: Source;
  index: number;
  selected: boolean;
  onOpen: () => void;
}) {
  return (
    <button className={`sourceChip ${selected ? "cited" : ""}`} onClick={onOpen}>
      <span className="sourceNumber" aria-hidden="true">
        {index}
      </span>
      <span className="sourceText">
        <strong>{source.filename}</strong>
        <small>
          {source.section ?? (source.page ? `Página ${source.page}` : "Sin paginación")}
          {selected ? ", citada" : ", recuperada sin citar"}
        </small>
      </span>
    </button>
  );
}

const ORIGIN = /^Según (.+):$/;

function Inline({
  text,
  sources,
  onSource,
}: {
  text: string;
  sources: Source[];
  onSource: (s: Source, index: number) => void;
}) {
  return (
    <>
      {text.split(/(\[\d+\])/g).map((part, j) => {
        const match = part.match(/^\[(\d+)\]$/);
        const n = match ? Number(match[1]) : 0;
        return n > 0 && sources[n - 1] ? (
          <button
            className="inlineCitation"
            key={j}
            aria-label={`Abrir fuente ${n}`}
            onClick={() => onSource(sources[n - 1], n)}
          >
            {n}
          </button>
        ) : (
          part
        );
      })}
    </>
  );
}

// React renders text only. No HTML/Markdown execution from untrusted documents.
export const AnswerText = memo(function AnswerText({
  text,
  sources,
  onSource,
}: {
  text: string;
  sources: Source[];
  onSource: (s: Source, index: number) => void;
}) {
  const blocks = text.split(/(```[\s\S]*?```)/g);
  return (
    <div className="answerText">
      {blocks.map((block, i) =>
        block.startsWith("```") ? (
          <pre key={i}>
            <code>{block.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}</code>
          </pre>
        ) : (
          <div key={i} className="answerBlock">
            {block.split("\n").map((line, k) => {
              const origin = line.match(ORIGIN);
              return origin ? (
                <span className="answerOrigin" key={k}>
                  Según <cite>{origin[1]}</cite>
                </span>
              ) : (
                <span className={line.startsWith("«") ? "answerQuote" : "answerLine"} key={k}>
                  <Inline text={line} sources={sources} onSource={onSource} />
                </span>
              );
            })}
          </div>
        ),
      )}
    </div>
  );
});

export function Insufficient({ text, kind }: { text: string; kind?: "verification" }) {
  return (
    <div className={`insufficient ${kind ?? ""}`}>
      <AlertCircle size={18} aria-hidden="true" />
      <div>
        <strong>
          {kind === "verification"
            ? "Comprobación de evidencia incompleta"
            : "Evidencia insuficiente o en conflicto"}
        </strong>
        <p>{text}</p>
        <small>
          {kind === "verification"
            ? "El modelo no terminó de evaluar los pasajes. Vuelve a intentarlo; no significa que falte documentación."
            : "Prueba una pregunta más concreta o añade documentación que cubra el dato."}
        </small>
      </div>
    </div>
  );
}
