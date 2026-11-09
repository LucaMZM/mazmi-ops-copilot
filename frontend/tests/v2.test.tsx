import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Copilot } from "../src/components/copilot";

const account = {
  email: "me@example.com",
  workspace_id: "w",
  workspaces: [{ id: "w", name: "Operaciones" }],
};

function mount() {
  render(<Copilot account={account} onSignOut={async () => {}} onWorkspace={async () => {}} />);
}

function sse(...events: unknown[]) {
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

const result = (answer: string, extra = {}) => ({
  type: "done",
  data: { conversation_id: "c1", answer, sources: [], pending_action: null, ...extra },
});

test("retrying a recovered message reuses its request id so the server can replay", async () => {
  const bodies: Record<string, unknown>[] = [];
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (String(input) === "/api/chat/stream") {
      bodies.push(JSON.parse(String(init?.body)));
      calls += 1;
      // First attempt: the connection drops before the terminal event.
      return calls === 1 ? sse({ type: "status", text: "Buscando fuentes…" }) : sse(result("Hecho"));
    }
    return Response.json([]);
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Copilot" }));
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), { target: { value: "Crea un ticket" } });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await screen.findByText("Recuperar mensaje para reintentar");
  expect(screen.getByRole("alert")).toHaveTextContent("Se interrumpió la respuesta");
  fireEvent.click(screen.getByText("Recuperar mensaje para reintentar"));
  expect(screen.getByLabelText("Mensaje al copiloto")).toHaveValue("Crea un ticket");
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await screen.findByText("Hecho");
  expect(bodies).toHaveLength(2);
  expect(bodies[1].client_request_id).toBe(bodies[0].client_request_id);
  expect(typeof bodies[0].client_request_id).toBe("string");
});

test("a new message gets a new request id", async () => {
  const ids: unknown[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (String(input) === "/api/chat/stream") {
      ids.push(JSON.parse(String(init?.body)).client_request_id);
      return sse(result(`Respuesta ${ids.length}`));
    }
    return Response.json([]);
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Copilot" }));
  for (const text of ["Primera", "Segunda"]) {
    fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), { target: { value: text } });
    fireEvent.click(screen.getByLabelText("Enviar mensaje"));
    await screen.findByText(`Respuesta ${ids.length}`);
  }
  expect(new Set(ids).size).toBe(2);
});

test("an already-resolved approval reports the real state instead of an error", async () => {
  const action = {
    id: "a1",
    name: "create_ticket",
    status: "PENDING",
    payload: { title: "Revisar acceso", description: "Alcance", priority: "HIGH" },
  };
  let resolved = false;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/decision")) {
      resolved = true;
      return Response.json({ detail: "La acción ya fue resuelta (ejecutada)." }, { status: 409 });
    }
    if (url === "/api/actions") return Response.json([{ ...action, status: resolved ? "EXECUTED" : "PENDING" }]);
    return Response.json([]);
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Aprobaciones" }));
  fireEvent.click(await screen.findByText("Confirmar"));
  await screen.findByText(/La acción ya fue resuelta/);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("Confirmar")).not.toBeInTheDocument());
});

test("streamed status comes from the server and the composer stays usable after completion", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/chat/stream"
      ? sse(
          { type: "status", text: "Comprobando suficiencia de la evidencia…" },
          { type: "delta", text: "Según politica.md:\n«Texto literal.» [1]" },
          result("Según politica.md:\n«Texto literal.» [1]", {
            sources: [{ chunk_id: 9, filename: "politica.md", page: null, excerpt: "Texto literal.", score: 0.8, section: "Vacaciones" }],
          }),
        )
      : Response.json([]),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Copilot" }));
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), { target: { value: "¿Vacaciones?" } });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  fireEvent.click(await screen.findByLabelText("Abrir fuente 1"));
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveTextContent("Vacaciones");
  expect(dialog).toHaveTextContent("Texto literal.");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.getByLabelText("Mensaje al copiloto")).toBeEnabled();
});

test("conversations can be renamed and archived from the open chat", async () => {
  const patches: unknown[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/conversations") return Response.json([{ id: "c1", title: "Consulta antigua" }]);
    if (url === "/api/conversations/c1" && init?.method === "PATCH") {
      patches.push(JSON.parse(String(init.body)));
      return Response.json({ id: "c1", title: "Nuevo título", archived: false });
    }
    if (url === "/api/conversations/c1")
      return Response.json({ messages: [{ role: "user", content: "Hola", sources: [] }], pending_actions: [] });
    return Response.json([]);
  });
  mount();
  fireEvent.click((await screen.findAllByRole("button", { name: "Consulta antigua" }))[0]);
  fireEvent.click(await screen.findByLabelText("Renombrar conversación"));
  fireEvent.change(screen.getByLabelText("Nuevo título de la conversación"), { target: { value: "Nuevo título" } });
  fireEvent.click(screen.getByText("Guardar"));
  await waitFor(() => expect(patches).toEqual([{ title: "Nuevo título" }]));
  fireEvent.click(await screen.findByLabelText("Archivar conversación"));
  await screen.findByText(/Conversación archivada/);
  expect(patches[1]).toEqual({ archived: true });
});
