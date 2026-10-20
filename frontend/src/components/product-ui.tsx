"use client";
import { useEffect, useRef, type ReactNode } from "react";
import {
  ArrowRight,
  Check,
  X,
  FileText,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import type { PendingAction, Source } from "./product-types";

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="emptyState">
      <div className="emptyMark">
        <FileText size={23} />
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Badge({
  state,
  children,
}: {
  state: string;
  children: ReactNode;
}) {
  return <span className={`badge ${state}`}>{children}</span>;
}
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
    <article className="actionCard">
      <div className="actionEyebrow">
        <ShieldCheck size={16} />
        <span>PROPUESTA · TODAVÍA NO EJECUTADA</span>
      </div>
      <h3>{action.payload.title}</h3>
      <p>{action.payload.description}</p>
      <dl className="inlineMetadata">
        <div>
          <dt>Herramienta</dt>
          <dd>Crear ticket interno</dd>
        </div>
        <div>
          <dt>Prioridad</dt>
          <dd>{action.payload.priority}</dd>
        </div>
      </dl>
      <p className="approvalNote">
        Al confirmar se creará un ticket en este workspace. Tu decisión quedará
        registrada.
      </p>
      <div className="actionButtons">
        <button disabled={busy} onClick={() => onDecide(action, false)}>
          <X size={16} /> Rechazar
        </button>
        <button
          className="primary"
          disabled={busy}
          onClick={() => onDecide(action, true)}
        >
          <Check size={16} /> Confirmar
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
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === root.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last ||
            document.activeElement === root.current)
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
        className="inspector"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">INSPECTOR DE CONOCIMIENTO</span>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="iconButton"
            aria-label="Cerrar inspector"
            onClick={onClose}
          >
            <X size={21} />
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
    <button
      className={`sourceChip ${selected ? "cited" : ""}`}
      onClick={onOpen}
    >
      <span className="sourceNumber">{index}</span>
      <span>
        <strong>{source.filename}</strong>
        <small>
          {source.page ? `Página ${source.page}` : "Sin paginación"} ·{" "}
          {selected ? "Citada en la respuesta" : "Recuperada, sin citar"}
        </small>
      </span>
      <ArrowRight size={15} />
    </button>
  );
}

// React renders text only. No HTML/Markdown execution from untrusted documents.
export function AnswerText({
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
            <code>
              {block.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}
            </code>
          </pre>
        ) : (
          <span key={i}>
            {block.split(/(\[\d+\])/g).map((part, j) => {
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
          </span>
        ),
      )}
    </div>
  );
}
export function Insufficient({ text }: { text: string }) {
  return (
    <div className="insufficient">
      <AlertCircle size={18} />
      <div>
        <strong>Evidencia insuficiente o en conflicto</strong>
        <p>{text}</p>
        <small>
          Prueba una pregunta más concreta o añade documentación que cubra el
          dato.
        </small>
      </div>
    </div>
  );
}
