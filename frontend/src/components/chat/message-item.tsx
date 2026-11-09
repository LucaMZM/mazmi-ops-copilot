"use client";
import { memo } from "react";
import { ActionCard, AnswerText, Insufficient, SourceChip, Spinner } from "../product-ui";
import type { Message, PendingAction, Source } from "../product-types";
import type { Draft } from "@/hooks/use-chat";
import { isAbstention } from "@/lib/format";

type Props = {
  message: Message;
  demo: boolean;
  deciding: boolean;
  onSource: (source: Source) => void;
  onDecide: (action: PendingAction, approved: boolean) => void;
};

/** One committed message. Memoized: streaming and typing never re-render history. */
export const MessageItem = memo(function MessageItem({
  message: m,
  demo,
  deciding,
  onSource,
  onDecide,
}: Props) {
  const cited = new Set(
    Array.from(m.content.matchAll(/\[(\d+)\]/g), (match) => Number(match[1])),
  );
  const verificationFailure = m.content.startsWith("No he podido completar la comprobación");
  return (
    <article className={`messageRow ${m.role} ${m.failed ? "failed" : ""}`}>
      <div className="messageIdentity">
        {m.role === "user" ? "Tú" : demo ? "MAZMI demo" : "MAZMI"}
        {m.role === "assistant" && m.sources?.length ? (
          <span className="identityHint">Respuesta documental</span>
        ) : null}
      </div>
      <div className="messageBody">
        {m.role === "assistant" && isAbstention(m.content) ? (
          <Insufficient
            text={m.content}
            kind={verificationFailure ? "verification" : undefined}
          />
        ) : (
          <AnswerText text={m.content} sources={m.sources ?? []} onSource={onSource} />
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
                  onOpen={() => onSource(source)}
                />
              ))}
            </div>
          </section>
        )}
        {m.pending && <ActionCard action={m.pending} busy={deciding} onDecide={onDecide} />}
      </div>
    </article>
  );
});

/** The in-flight answer: progress from real server stages, then streamed text. */
export function DraftMessage({ draft, demo }: { draft: Draft; demo: boolean }) {
  return (
    <article className="messageRow assistant draft" aria-busy="true">
      <div className="messageIdentity">{demo ? "MAZMI demo" : "MAZMI"}</div>
      <div className="messageBody">
        {draft.text ? <div className="answerText streamingText">{draft.text}</div> : null}
        <div className="streamStatus" role="status">
          <Spinner /> {draft.status || "Procesando…"}
        </div>
      </div>
    </article>
  );
}
