"use client";
import { forwardRef, useRef, type ReactNode } from "react";
import { ArrowDown } from "lucide-react";
import { Composer, type ComposerHandle } from "./composer";
import { DraftMessage, MessageItem } from "./message-item";
import type { Message, Mode, PendingAction, Source, SystemInfo } from "../product-types";
import type { Draft } from "@/hooks/use-chat";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";

const STARTERS = ["¿Qué dice la documentación sobre ", "Lista los tickets del workspace"];

type Props = {
  system: SystemInfo | null;
  messages: Message[];
  draft: Draft | null;
  loadingHistory: boolean;
  deciding: boolean;
  mode: Mode;
  onMode: (mode: Mode) => void;
  listening: boolean;
  onSend: (text: string) => Promise<boolean>;
  onStop: () => void;
  onListen: () => void;
  onSource: (source: Source) => void;
  onDecide: (action: PendingAction, approved: boolean) => void;
  feedback: ReactNode;
  context: ReactNode;
};

export const ChatView = forwardRef<ComposerHandle, Props>(function ChatView(
  {
    system,
    messages,
    draft,
    loadingHistory,
    deciding,
    mode,
    onMode,
    listening,
    onSend,
    onStop,
    onListen,
    onSource,
    onDecide,
    feedback,
    context,
  },
  composerRef,
) {
  const scroller = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const { onScroll, jump, hasUnseen, follow } = useStickToBottom(
    scroller,
    end,
    `${messages.length}:${draft?.text.length ?? -1}:${draft?.status ?? ""}:${loadingHistory}`,
  );
  const streaming = draft !== null;

  return (
    <div className="chatLayout">
      <div
        ref={scroller}
        id="main-content"
        tabIndex={-1}
        className="chatScroll"
        onScroll={onScroll}
        aria-busy={loadingHistory || streaming}
      >
        <div className="chatColumn">
          {context}
          {feedback}
          {!messages.length && !streaming && (
            <section className="chatWelcome" aria-labelledby="welcome-title">
              <h2 id="welcome-title">¿Qué necesitas saber o resolver?</h2>
              <p>
                Pregunta a los documentos de este workspace y verifica cada cita, o prepara
                una acción que solo se ejecuta cuando tú la confirmas.
              </p>
              <div className="promptList">
                {STARTERS.map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      if (composerRef && "current" in composerRef) composerRef.current?.setText(t);
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
              {system?.generation.verification === "failed" && (
                <p className="setupHint">
                  La última prueba de Ollama falló. Las lecturas exactas de tickets funcionan sin
                  modelo; para preguntas documentales inicia Ollama y revisa Configuración.
                </p>
              )}
            </section>
          )}
          {loadingHistory && (
            <p className="streamStatus" role="status">
              Cargando la conversación…
            </p>
          )}
          {messages.map((m) => (
            <MessageItem
              key={m.id}
              message={m}
              deciding={deciding}
              onSource={onSource}
              onDecide={onDecide}
            />
          ))}
          {draft && <DraftMessage draft={draft} />}
          <div ref={end} className="scrollAnchor" />
        </div>
      </div>
      {hasUnseen && (
        <button className="jumpLatest glass" onClick={() => jump()}>
          <ArrowDown size={15} aria-hidden="true" /> Ir al último mensaje
        </button>
      )}
      <Composer
        ref={composerRef}
        mode={mode}
        onMode={onMode}
        busy={streaming || loadingHistory}
        streaming={streaming}
        blocked={deciding}
        listening={listening}
        onSend={(text) => {
          follow();
          return onSend(text);
        }}
        onStop={onStop}
        onListen={onListen}
      />
    </div>
  );
});
