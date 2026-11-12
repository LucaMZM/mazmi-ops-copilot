"use client";
import { forwardRef, useLayoutEffect, useRef, type ReactNode } from "react";
import { ArrowDown, FileSearch, ListChecks } from "lucide-react";
import { Composer, type ComposerHandle } from "./composer";
import { DraftMessage, MessageItem } from "./message-item";
import type { Message, Mode, PendingAction, Source, SystemInfo } from "../product-types";
import type { Draft } from "@/hooks/use-chat";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import { RobotMark } from "../brand/robot-mark";

const STARTERS = [
  { text: "¿Qué dice la documentación sobre ", icon: FileSearch },
  { text: "Lista los tickets del workspace", icon: ListChecks },
];

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
  const slot = useRef<HTMLDivElement>(null);
  const fromTop = useRef<number | null>(null);
  const { onScroll, jump, hasUnseen, follow } = useStickToBottom(
    scroller,
    end,
    `${messages.length}:${draft?.text.length ?? -1}:${draft?.status ?? ""}:${loadingHistory}`,
  );
  const streaming = draft !== null;
  const empty = !messages.length && !streaming && !loadingHistory;

  // The composer starts in the middle of an empty conversation. When the first message
  // leaves, it travels to the bottom (FLIP, transform only) instead of jumping there.
  useLayoutEffect(() => {
    const el = slot.current;
    const from = fromTop.current;
    fromTop.current = null;
    if (empty || !el || from === null || typeof el.animate !== "function") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;
    const delta = from - el.getBoundingClientRect().top;
    if (Math.abs(delta) < 2) return;
    el.animate([{ transform: `translateY(${delta}px)` }, { transform: "translateY(0)" }], {
      duration: 360,
      easing: "cubic-bezier(0.32, 0.72, 0, 1)",
    });
  }, [empty]);

  const setText = (text: string) => {
    if (composerRef && "current" in composerRef) composerRef.current?.setText(text);
  };

  return (
    <div className={`chatLayout ${empty ? "isEmpty" : ""}`}>
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
          {empty && (
            <section className="chatWelcome" aria-labelledby="welcome-title">
              <span className="welcomeMark" aria-hidden="true">
                <RobotMark size={34} className="blinking" />
              </span>
              <h2 id="welcome-title">¿Qué necesitas saber o resolver?</h2>
              <p>
                Pregunta a los documentos de este workspace y verifica cada cita, o prepara
                una acción que solo se ejecuta cuando tú la confirmas.
              </p>
              {system?.generation.verification === "failed" && (
                <p className="setupHint">
                  La última prueba de Ollama falló. Las lecturas exactas de tickets funcionan sin
                  modelo; para preguntas documentales inicia Ollama y revisa Configuración.
                </p>
              )}
            </section>
          )}
          {loadingHistory && (
            <p className="streamStatus historyStatus" role="status">
              <RobotMark size={18} className="thinking" /> Cargando la conversación…
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
        <button className="jumpLatest" onClick={() => jump()}>
          <ArrowDown size={15} aria-hidden="true" /> Ir al último mensaje
        </button>
      )}
      <div ref={slot} className="composerSlot">
        <Composer
          ref={composerRef}
          mode={mode}
          onMode={onMode}
          busy={streaming || loadingHistory}
          streaming={streaming}
          blocked={deciding}
          listening={listening}
          onSend={(text) => {
            if (empty && slot.current) fromTop.current = slot.current.getBoundingClientRect().top;
            follow();
            return onSend(text);
          }}
          onStop={onStop}
          onListen={onListen}
        />
      </div>
      {empty && (
        <div className="promptList" role="group" aria-label="Sugerencias">
          {STARTERS.map(({ text, icon: Icon }) => (
            <button key={text} onClick={() => setText(text)}>
              <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
              {text.endsWith(" ") ? `${text.trim()}…` : text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
});
