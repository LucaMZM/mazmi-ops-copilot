"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, request, requestId } from "@/lib/api";
import { readChatStream, StreamError } from "@/lib/sse";
import type {
  ChatResult,
  Message,
  Mode,
  PendingAction,
} from "@/components/product-types";

export type Draft = { text: string; status: string };
type Retry = { text: string; requestId: string };

let messageSeq = 0;
const nextId = () => `m${++messageSeq}`;

const CHAT_TIMEOUT_MS = 300_000;

/**
 * Conversation state machine.
 *
 * - Committed messages live in `messages`; the in-flight answer lives in `draft`, so a
 *   streaming update re-renders one component instead of the whole history.
 * - Deltas are buffered and flushed at most once per animation frame.
 * - Each submitted turn carries a `client_request_id`. Recovering a failed message and
 *   sending it unchanged reuses that id, so if the server had already committed the
 *   turn it replays the result instead of acting twice.
 */
export function useChat(options: { onSettled?: (result: ChatResult | null) => void } = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"idle" | "streaming" | "loading">("idle");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState<Retry | null>(null);
  const controller = useRef<AbortController | null>(null);
  const pendingText = useRef("");
  const frame = useRef<number | null>(null);
  const recovered = useRef<Retry | null>(null);
  const settled = useRef(options.onSettled);
  const alive = useRef(true);

  useEffect(() => {
    settled.current = options.onSettled;
  });
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      controller.current?.abort();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, []);

  const flush = useCallback(() => {
    frame.current = null;
    const chunk = pendingText.current;
    pendingText.current = "";
    if (chunk) setDraft((d) => (d ? { ...d, text: d.text + chunk } : d));
  }, []);

  const queueDelta = useCallback(
    (text: string) => {
      pendingText.current += text;
      if (frame.current === null) frame.current = requestAnimationFrame(flush);
    },
    [flush],
  );

  const send = useCallback(
    async (text: string, mode: Mode) => {
      const message = text.trim();
      if (!message || controller.current) return false;
      const reused = recovered.current?.text === message ? recovered.current : null;
      const id = reused?.requestId ?? requestId();
      recovered.current = null;
      const abort = new AbortController();
      controller.current = abort;
      const timeout = setTimeout(
        () => abort.abort(new DOMException("Timeout", "TimeoutError")),
        CHAT_TIMEOUT_MS,
      );
      setError("");
      setRetry(null);
      setBusy("streaming");
      setMessages((m) => [...m, { id: nextId(), role: "user", content: message }]);
      setDraft({ text: "", status: "Enviando consulta…" });
      let result: ChatResult | null = null;
      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          signal: abort.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            conversation_id: conversationId,
            mode,
            client_request_id: id,
          }),
        });
        result = await readChatStream<ChatResult>(response, (event) => {
          if (!alive.current) return;
          if (event.type === "delta") queueDelta(event.text);
          if (event.type === "status") setDraft((d) => (d ? { ...d, status: event.text } : d));
        });
        if (frame.current !== null) cancelAnimationFrame(frame.current);
        pendingText.current = "";
        frame.current = null;
        const done = result;
        if (!alive.current) return true;
        setConversationId(done.conversation_id);
        setMessages((m) => [
          ...m,
          {
            id: nextId(),
            role: "assistant",
            content: done.answer,
            sources: done.sources,
            pending: done.pending_action ?? undefined,
          },
        ]);
        return true;
      } catch (err) {
        if (!alive.current) return false;
        const reason =
          abort.signal.aborted && abort.signal.reason instanceof DOMException
            ? abort.signal.reason
            : err;
        setError(errorMessage(reason));
        // Keep the id: an unchanged resend may replay a turn the server already saved.
        setRetry({ text: message, requestId: id });
        const incomplete = err instanceof StreamError && err.incomplete;
        setMessages((m) => [
          ...m,
          {
            id: nextId(),
            role: "assistant",
            failed: true,
            content: incomplete
              ? "La respuesta se interrumpió. Revisa el historial antes de repetir una acción."
              : "La respuesta no se completó. Revisa el historial antes de repetir una acción.",
          },
        ]);
        return false;
      } finally {
        clearTimeout(timeout);
        controller.current = null;
        if (alive.current) {
          setDraft(null);
          setBusy("idle");
          settled.current?.(result);
        }
      }
    },
    [conversationId, queueDelta],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  /** Put the failed message back in the composer; resending it reuses its request id. */
  const recover = useCallback(() => {
    if (!retry) return "";
    recovered.current = retry;
    setRetry(null);
    return retry.text;
  }, [retry]);

  const open = useCallback(async (id: string) => {
    if (controller.current) return false;
    setBusy("loading");
    setError("");
    try {
      const data = await request<{ messages: Message[]; pending_actions: PendingAction[] }>(
        `/api/conversations/${id}`,
      );
      if (!alive.current) return false;
      setMessages([
        ...data.messages.map((m) => ({ ...m, id: nextId() })),
        ...data.pending_actions.map((pending) => ({
          id: nextId(),
          role: "assistant" as const,
          content: "Acción pendiente de confirmación.",
          pending,
        })),
      ]);
      setConversationId(id);
      return true;
    } catch (err) {
      if (alive.current) setError(errorMessage(err));
      return false;
    } finally {
      if (alive.current) setBusy("idle");
    }
  }, []);

  const reset = useCallback(() => {
    if (controller.current) return;
    setMessages([]);
    setConversationId(null);
    setError("");
    setRetry(null);
  }, []);

  /** Replace a resolved proposal with its committed receipt. */
  const resolveAction = useCallback((actionId: string, receipt: string) => {
    setMessages((m) => [
      ...m.map((item) =>
        item.pending?.id === actionId ? { ...item, pending: undefined } : item,
      ),
      { id: nextId(), role: "assistant", content: receipt },
    ]);
  }, []);

  return {
    messages,
    draft,
    conversationId,
    busy,
    error,
    setError,
    retry,
    send,
    stop,
    recover,
    open,
    reset,
    resolveAction,
  };
}
