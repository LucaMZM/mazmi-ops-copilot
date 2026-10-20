import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Copilot } from "../src/components/copilot";
const account = {
  email: "me@example.com",
  workspace_id: "w",
  workspaces: [{ id: "w", name: "Team" }],
};
function mount() {
  const result = render(
    <Copilot
      account={account}
      onSignOut={async () => {}}
      onWorkspace={async () => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Copilot" }));
  return result;
}
function streamed(data: unknown) {
  const bytes = new TextEncoder().encode(
    `data: ${JSON.stringify({ type: "done", data })}\n\n`,
  );
  return new Response(
    new ReadableStream({
      start(c) {
        c.enqueue(bytes);
        c.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}
test("ASK/DO, sources and pending action require explicit approval", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/chat/stream") {
        expect(JSON.parse(String(init?.body)).mode).toBe("DO");
        return streamed({
          conversation_id: "c",
          answer: "Propuesta [1]",
          sources: [
            {
              chunk_id: 1,
              filename: "policy.pdf",
              page: 2,
              excerpt: "Approval required",
              score: 0.9,
            },
          ],
          pending_action: {
            id: "a",
            name: "create_ticket",
            payload: {
              title: "Ticket de prueba",
              description: "Revisar acceso",
              priority: "HIGH",
            },
          },
        });
      }
      if (url.includes("/decision"))
        return Response.json({
          status: "executed",
          ticket: { id: 42, title: "Ticket de prueba" },
        });
      return Response.json([]);
    });
  mount();
  await screen.findByText("Datos del workspace actual");
  expect(screen.getByRole("button", { name: "ASK" })).toHaveClass("selected");
  fireEvent.click(screen.getByRole("button", { name: "DO" }));
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Crea ticket" },
  });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await screen.findByText("Ticket de prueba");
  expect(
    fetcher.mock.calls.some(([u]) => String(u).includes("/decision")),
  ).toBe(false);
  fireEvent.click(screen.getByLabelText("Abrir fuente 1"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Approval required");
  fireEvent.click(screen.getByLabelText("Cerrar inspector"));
  fireEvent.click(screen.getByText("Confirmar"));
  await screen.findByText(/Ticket #42/);
  expect(screen.queryByText("Confirmar")).not.toBeInTheDocument();
});
test("backend failure shows an error and allows retry", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input).includes("/stream")
      ? Response.json({ detail: "Proveedor no disponible" }, { status: 503 })
      : Response.json([]),
  );
  mount();
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Pregunta" },
  });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Proveedor no disponible",
    ),
  );
  fireEvent.click(screen.getByText("Recuperar mensaje para reintentar"));
  expect(screen.getByLabelText("Mensaje al copiloto")).toHaveValue("Pregunta");
});

test("failed approval never appears as executed", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/stream"))
      return streamed({
        conversation_id: "c",
        answer: "Propuesta",
        sources: [],
        pending_action: {
          id: "a",
          name: "create_ticket",
          payload: {
            title: "Acceso",
            description: "Solicitud",
            priority: "HIGH",
          },
        },
      });
    if (url.includes("/decision"))
      return Response.json(
        { detail: "La acción ya fue resuelta" },
        { status: 409 },
      );
    return Response.json([]);
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "DO" }));
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Crea ticket" },
  });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  fireEvent.click(await screen.findByText("Confirmar"));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "La acción ya fue resuelta",
    ),
  );
  expect(screen.queryByText(/Acción ejecutada/)).not.toBeInTheDocument();
});

test("upload failure is visible in Knowledge", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
    init?.body instanceof FormData
      ? Response.json({ detail: "Documento sin texto" }, { status: 422 })
      : Response.json([]),
  );
  const { container } = mount();
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: {
      files: [new File(["bad"], "scan.pdf", { type: "application/pdf" })],
    },
  });
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Documento sin texto"),
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Knowledge",
  );
});

test("Enter cannot send while a conversation is loading", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      if (String(input) === "/api/conversations")
        return Response.json([{ id: "c", title: "Conversación guardada" }]);
      if (String(input) === "/api/conversations/c")
        return new Promise<Response>(() => {});
      return Response.json([]);
    });
  mount();
  fireEvent.click(await screen.findByText("Conversación guardada"));
  const field = screen.getByLabelText("Mensaje al copiloto");
  fireEvent.change(field, { target: { value: "No enviar todavía" } });
  fireEvent.keyDown(field, { key: "Enter" });
  expect(
    fetcher.mock.calls.some(([url]) => String(url).includes("/stream")),
  ).toBe(false);
});

test("missing microphone support leaves text chat usable", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json([]));
  mount();
  fireEvent.click(screen.getByLabelText("Activar micrófono"));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Grabación no disponible",
    ),
  );
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Sigo escribiendo" },
  });
  expect(screen.getByLabelText("Enviar mensaje")).toBeEnabled();
});

test("reindex requires confirmation and calls the scoped document endpoint", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      if (init?.method === "POST") return Response.json({ status: "ready" });
      return Response.json(
        String(input) === "/api/documents"
          ? [
              {
                id: "doc1",
                filename: "Policy.txt",
                pages: 1,
                chunks: 1,
                status: "ready",
                size_bytes: 12,
                mime_type: "text/plain",
                created_at: "2026-10-18T12:00:00Z",
                error: null,
              },
            ]
          : [],
      );
    });
  mount();
  fireEvent.click(screen.getByRole("button", { name: /Knowledge/ }));
  fireEvent.click(await screen.findByText("Reindexar"));
  await screen.findByText("Documento reindexado con el modelo configurado.");
  expect(window.confirm).toHaveBeenCalledTimes(1);
  expect(
    fetcher.mock.calls.some(
      ([url, init]) =>
        url === "/api/documents/doc1/reindex" && init?.method === "POST",
    ),
  ).toBe(true);
});
