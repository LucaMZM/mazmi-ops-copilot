import { expect, test } from "vitest";
import { ApiError } from "../src/lib/api";
import { parseFrame, readChatStream, StreamError, type StreamEvent } from "../src/lib/sse";

function chunked(parts: (string | Uint8Array)[]) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(c) {
        for (const part of parts) c.enqueue(typeof part === "string" ? encoder.encode(part) : part);
        c.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

const done = (data: unknown) => `data: ${JSON.stringify({ type: "done", data })}\n\n`;

test("frames split across chunks, CRLF and heartbeats are parsed", async () => {
  const events: StreamEvent<{ ok: boolean }>[] = [];
  const status = 'data: {"type":"status","text":"Buscando fuentes…"}\r\n\r\n';
  const cr = status.indexOf("\r") + 1; // Chunk boundary between CR and LF.
  const result = await readChatStream<{ ok: boolean }>(
    chunked([": stream-open\n\n", status.slice(0, 17), status.slice(17, cr), status.slice(cr), ": keep-alive\n\n", done({ ok: true })]),
    (e) => events.push(e),
  );
  expect(result).toEqual({ ok: true });
  expect(events.map((e) => e.type)).toEqual(["status", "done"]);
  expect(events[0]).toMatchObject({ text: "Buscando fuentes…" });
});

test("a multi-byte character split between chunks is decoded intact", async () => {
  const bytes = new TextEncoder().encode('data: {"type":"delta","text":"Según"}\n\n');
  const cut = bytes.indexOf(0xc3) + 1; // Inside the two-byte "ú".
  const events: StreamEvent<unknown>[] = [];
  await readChatStream(chunked([bytes.slice(0, cut), bytes.slice(cut), done({})]), (e) => events.push(e));
  expect(events[0]).toEqual({ type: "delta", text: "Según" });
});

test("multi-line data fields and a final frame without blank line", async () => {
  expect(parseFrame('data: {"a":\ndata: 1}')).toBe('{"a":\n1}');
  expect(parseFrame(": comment only")).toBeNull();
  const result = await readChatStream<number>(chunked(['data: {"type":"done","data":7}']), () => {});
  expect(result).toBe(7);
});

test("a stream that ends without done is incomplete, never success", async () => {
  const error = await readChatStream(chunked(['data: {"type":"delta","text":"Hola"}\n\n']), () => {}).catch(
    (e) => e,
  );
  expect(error).toBeInstanceOf(StreamError);
  expect((error as StreamError).incomplete).toBe(true);
});

test("server error events and unreadable frames are reported", async () => {
  const failed = await readChatStream(
    chunked(['data: {"type":"error","message":"Conversación no encontrada","status":404}\n\n']),
    () => {},
  ).catch((e) => e);
  expect(failed).toMatchObject({ message: "Conversación no encontrada", status: 404 });
  const garbage = await readChatStream(chunked(["data: {not json\n\n"]), () => {}).catch((e) => e);
  expect(garbage).toBeInstanceOf(StreamError);
});

test("HTTP errors keep their status and server detail", async () => {
  const error = await readChatStream(
    Response.json({ detail: "Proveedor no configurado" }, { status: 503 }),
    () => {},
  ).catch((e) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 503, message: "Proveedor no configurado" });
});
