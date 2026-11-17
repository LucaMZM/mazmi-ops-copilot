"use client";
import { memo } from "react";
import { Activity } from "lucide-react";
import { ActionCard, AnswerText, Insufficient, SourceChip } from "../product-ui";
import type { Message, PendingAction } from "../product-types";
import type { Draft } from "@/hooks/use-chat";
import { isAbstention } from "@/lib/format";
import { RobotMark } from "../brand/robot-mark";

type Props = {
  message: Message;
  deciding: boolean;
  /** Opens the evidence explorer on source `index` (0-based) of this message. */
  onSource: (message: Message, index: number) => void;
  onDecide: (action: PendingAction, approved: boolean) => void;
  /** Present only in diagnostic mode, and only for answers that consulted documents. */
  onDiagnose?: (message: Message) => void;
};

/** One committed message. Memoized: streaming and typing never re-render history. */
export const MessageItem = memo(function MessageItem({
  message: m,
  deciding,
  onSource,
  onDecide,
  onDiagnose,
}: Props) {
  const cited = new Set(
    Array.from(m.content.matchAll(/\[(\d+)\]/g), (match) => Number(match[1])),
  );
  const verificationFailure = m.content.startsWith("No he podido completar la comprobación");
  return (
    <article
      className={`messageRow ${m.role} ${m.failed ? "failed" : ""} ${m.fresh ? "enter" : ""}`}
    >
      {m.role === "user" ? (
        <span className="srOnly">Tú:</span>
      ) : (
        <div className="messageIdentity">
          <RobotMark size={18} />
          MAZMI
          {m.sources?.length ? <span className="identityHint">Respuesta documental</span> : null}
        </div>
      )}
      <div className="messageBody">
        {m.role === "assistant" && isAbstention(m.content) ? (
          <Insufficient
            text={m.content}
            kind={verificationFailure ? "verification" : undefined}
          />
        ) : (
          <AnswerText
            text={m.content}
            sources={m.sources ?? []}
            onSource={(_, n) => onSource(m, n - 1)}
          />
        )}
        {m.failed && (
          <small className="errorText">
            Respuesta incompleta. No se ha confirmado ninguna ejecución desde este mensaje.
          </small>
        )}
        {m.sources && m.sources.length > 0 && (
          <section className="sources" aria-label="Evidencia recuperada">
            <h3 className="sourcesTitle">
              Evidencia recuperada ({m.sources.length}{" "}
              {m.sources.length === 1 ? "fragmento" : "fragmentos"})
            </h3>
            <div className="sourceGrid">
              {m.sources.map((source, j) => (
                <SourceChip
                  key={source.chunk_id}
                  source={source}
                  index={j + 1}
                  selected={cited.has(j + 1)}
                  onOpen={() => onSource(m, j)}
                />
              ))}
            </div>
          </section>
        )}
        {onDiagnose && m.role === "assistant" && m.sources && m.sources.length > 0 && (
          <button className="diagnoseButton" onClick={() => onDiagnose(m)}>
            <Activity size={14} strokeWidth={1.75} aria-hidden="true" /> Diagnóstico RAG
          </button>
        )}
        {m.pending && <ActionCard action={m.pending} busy={deciding} onDecide={onDecide} />}
      </div>
    </article>
  );
});

/** The in-flight answer: progress from real server stages, then streamed text. */
export function DraftMessage({ draft }: { draft: Draft }) {
  return (
    <article className="messageRow assistant draft" aria-busy="true">
      <div className="messageIdentity">
        <RobotMark size={18} className="thinking" />
        MAZMI
      </div>
      <div className="messageBody">
        {draft.text ? <div className="answerText streamingText">{draft.text}</div> : null}
        <div className="streamStatus" role="status">
          <span className="statusDots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          {draft.status || "Procesando…"}
        </div>
      </div>
    </article>
  );
}
