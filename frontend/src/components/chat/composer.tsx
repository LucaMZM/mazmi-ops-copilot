"use client";
import { forwardRef, useImperativeHandle, useRef, useState, type FormEvent } from "react";
import { ArrowUp, Mic, Square } from "lucide-react";
import type { Mode } from "../product-types";

export type ComposerHandle = { setText: (text: string) => void; focus: () => void };

type Props = {
  mode: Mode;
  onMode: (mode: Mode) => void;
  busy: boolean;
  streaming: boolean;
  blocked: boolean;
  listening: boolean;
  onSend: (text: string) => Promise<boolean>;
  onStop: () => void;
  onListen: () => void;
};

/**
 * The composer owns its draft text, so each keystroke re-renders only this component.
 * The capsule's tint follows the mode: understanding (ASK) or preparing an action (DO).
 */
export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { mode, onMode, busy, streaming, blocked, listening, onSend, onStop, onListen },
  ref,
) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({
    setText: (value: string) => {
      setText(value);
      area.current?.focus();
    },
    focus: () => area.current?.focus(),
  }));

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const value = text.trim();
    if (!value || busy || blocked) return;
    setText("");
    const ok = await onSend(value);
    if (!ok) area.current?.focus();
  }

  return (
    <div className={`composerDock mode-${mode.toLowerCase()}`}>
      <form className="composer glass" onSubmit={submit}>
        <div className="modeSwitch" role="group" aria-label="Modo de trabajo">
          <span className="modeThumb" aria-hidden="true" />
          {(["ASK", "DO"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={mode === value}
              className={mode === value ? "selected" : ""}
              disabled={busy}
              onClick={() => onMode(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <textarea
          ref={area}
          aria-label="Mensaje al copiloto"
          aria-describedby="composer-hint"
          maxLength={8000}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            mode === "ASK" ? "Pregunta a la documentación del workspace" : "Describe la acción que necesitas"
          }
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="composerTools">
          <button
            type="button"
            className={`iconButton mic ${listening ? "recording" : ""}`}
            disabled={busy}
            aria-pressed={listening}
            aria-label={listening ? "Detener micrófono" : "Activar micrófono"}
            onClick={onListen}
          >
            {listening ? <Square size={16} /> : <Mic size={17} />}
          </button>
          {streaming ? (
            <button type="button" className="stopButton" onClick={onStop}>
              <Square size={13} aria-hidden="true" /> Detener consulta
            </button>
          ) : (
            <button
              aria-label="Enviar mensaje"
              className="send"
              disabled={!text.trim() || busy || blocked}
            >
              <ArrowUp size={18} />
            </button>
          )}
        </div>
      </form>
      <p id="composer-hint" className="composerHint">
        {listening
          ? "Grabando, máximo 60 segundos."
          : mode === "ASK"
            ? "ASK solo consulta: responde con pasajes citados o se abstiene."
            : "DO prepara acciones; ninguna se ejecuta sin tu confirmación."}
      </p>
    </div>
  );
});
