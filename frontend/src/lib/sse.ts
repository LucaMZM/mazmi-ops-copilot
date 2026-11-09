/**
 * Incremental Server-Sent Events reader for the chat stream.
 *
 * Handles what real networks do: frames split across chunks, multi-byte UTF-8
 * characters split across chunks, CRLF line endings, comment/heartbeat lines,
 * multi-line `data:` fields and a final frame without its trailing blank line.
 * A stream that ends without a terminal `done` event is an *incomplete* response and
 * is reported as such — never as success.
 */
import { ApiError, detailOf } from "./api";

export type StreamEvent<T> =
  | { type: "delta"; text: string }
  | { type: "status"; text: string; stage?: string }
  | { type: "done"; data: T }
  | { type: "error"; message: string; status?: number };

export class StreamError extends Error {
  readonly status?: number;
  readonly incomplete: boolean;
  constructor(message: string, options: { status?: number; incomplete?: boolean } = {}) {
    super(message);
    this.name = "StreamError";
    this.status = options.status;
    this.incomplete = options.incomplete ?? false;
  }
}

export const INCOMPLETE_MESSAGE =
  "Se interrumpió la respuesta antes de terminar. Revisa el historial antes de repetir una acción.";

/** Parse one SSE frame (without its separator). Returns null for comment-only frames. */
export function parseFrame(frame: string): string | null {
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") data.push(value);
  }
  return data.length ? data.join("\n") : null;
}

function decodeEvent<T>(payload: string): StreamEvent<T> {
  try {
    const event = JSON.parse(payload) as StreamEvent<T>;
    if (!event || typeof event !== "object" || typeof event.type !== "string")
      throw new Error("shape");
    return event;
  } catch {
    throw new StreamError("El servidor envió un evento ilegible. Puedes reintentar.");
  }
}

export async function readChatStream<T>(
  response: Response,
  onEvent: (event: StreamEvent<T>) => void,
): Promise<T> {
  if (!response.ok) throw new ApiError(await detailOf(response), response.status);
  if (!response.body) throw new StreamError("El servidor no devolvió una respuesta");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: { data: T } | null = null;

  const dispatch = (frame: string) => {
    const payload = parseFrame(frame);
    if (payload === null) return;
    const event = decodeEvent<T>(payload);
    if (event.type === "error") throw new StreamError(event.message, { status: event.status });
    if (event.type === "done") result = { data: event.data };
    onEvent(event);
  };

  let carriage = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      let text = carriage + decoder.decode(value, { stream: !done });
      // A CR at the end of a chunk may be the first half of a CRLF pair.
      carriage = !done && text.endsWith("\r") ? "\r" : "";
      if (carriage) text = text.slice(0, -1);
      buffer += text.replace(/\r\n?/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        dispatch(frame);
        if (result) return (result as { data: T }).data;
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (result) return (result as { data: T }).data;
    throw new StreamError(INCOMPLETE_MESSAGE, { incomplete: true });
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
