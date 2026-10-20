import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Copilot } from "../src/components/copilot";
import { AnswerText, Inspector } from "../src/components/product-ui";
import type { SystemInfo } from "../src/components/product-types";
const account = {
  email: "demo@test.local",
  workspace_id: "one",
  workspaces: [
    { id: "one", name: "Operaciones" },
    { id: "two", name: "Laboratorio" },
  ],
};
const system: SystemInfo = {
  demo: false,
  generation: {
    provider: "gemini",
    model: "gemini-test",
    state: "not_configured",
    verification: "not_checked",
  },
  embeddings: {
    provider: "gemini",
    model: "embedding-test",
    state: "not_configured",
    verification: "not_checked",
    dimensions: 768,
    collection: "gemini:test:768:v1",
  },
  voice: {
    stt: "faster-whisper",
    tts: "piper",
    stt_configured: false,
    tts_configured: false,
    verification: "not_checked",
  },
  indexing: {
    max_file_mb: 20,
    formats: ["txt"],
    strategy: "hybrid_rrf",
    top_k: 6,
  },
};
const docs = [
  {
    id: "a",
    filename: "Vacaciones.txt",
    status: "ready",
    chunks: 2,
    pages: 1,
    size_bytes: 500,
    created_at: "2026-10-20T12:00:00Z",
    mime_type: "text/plain",
    error: null,
    embedding_model: "embedding-test",
    embedding_collection: system.embeddings.collection,
    embedding_dimensions: 768,
  },
  {
    id: "b",
    filename: "Acceso-antiguo.txt",
    status: "ready",
    chunks: 1,
    pages: 1,
    size_bytes: 500,
    created_at: "2026-10-20T12:00:00Z",
    mime_type: "text/plain",
    error: null,
    embedding_model: "old-model",
    embedding_collection: "openai:old:1536",
    embedding_dimensions: 1536,
  },
  {
    id: "c",
    filename: "Sin-texto.pdf",
    status: "failed",
    chunks: 0,
    pages: 0,
    size_bytes: 500,
    created_at: "2026-10-20T12:00:00Z",
    mime_type: "application/pdf",
    error: "No contiene texto",
    embedding_collection: system.embeddings.collection,
  },
];
function fetchBase(path: string) {
  if (path === "/api/system") return system;
  if (path === "/api/documents") return docs;
  return [];
}
function mockBase() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) =>
      Response.json(fetchBase(String(input))),
    );
}
function mount() {
  return render(
    <Copilot
      account={account}
      onSignOut={async () => {}}
      onWorkspace={async () => {}}
    />,
  );
}
const nav = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name }));

test("workspace shows only ready compatible documents", async () => {
  mockBase();
  mount();
  await screen.findByText("Vacaciones.txt");
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Workspace",
  );
  expect(screen.queryByText("Acceso-antiguo.txt")).not.toBeInTheDocument();
  expect(screen.queryByText("Sin-texto.pdf")).not.toBeInTheDocument();
  expect(screen.getByText("Decisiones al día")).toBeInTheDocument();
});
test("knowledge searches filenames and filters incompatible and failed documents", async () => {
  mockBase();
  mount();
  nav("Knowledge");
  await screen.findByText("Acceso-antiguo.txt");
  fireEvent.change(screen.getByLabelText("Filtrar documentos"), {
    target: { value: "incompatible" },
  });
  expect(screen.queryByText("Vacaciones.txt")).not.toBeInTheDocument();
  expect(screen.getByText("Acceso-antiguo.txt")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Filtrar documentos"), {
    target: { value: "failed" },
  });
  expect(screen.getByText("No contiene texto")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Buscar documentos"), {
    target: { value: "No-existe" },
  });
  expect(screen.getByText("Sin coincidencias")).toBeInTheDocument();
});
test("settings distinguish missing config from real verification", async () => {
  mockBase();
  mount();
  nav("Configuración");
  await screen.findByText("gemini-test");
  expect(screen.getAllByText("No configurado").length).toBeGreaterThan(1);
  expect(screen.getAllByText("No verificada")).toHaveLength(2);
  expect(screen.queryByText(/Conectado/)).not.toBeInTheDocument();
  expect(screen.getByText("gemini:test:768:v1")).toBeInTheDocument();
});
test("demo state is clearly labeled without claiming a Gemini connection", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input) === "/api/system" ? { ...system, demo: true } : [],
    ),
  );
  mount();
  await screen.findByText("DEMO DE DESARROLLO");
  expect(
    screen.getByText(/IA simulada · Sin conexión con Gemini/),
  ).toBeInTheDocument();
});
test("document inspector calls scoped chunk endpoint and supports keyboard dismissal", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input).includes("/chunks")
        ? {
            filename: "Vacaciones.txt",
            total: 1,
            offset: 0,
            chunks: [
              {
                id: 5,
                index: 0,
                page: null,
                content: "Pasaje verificable y completo",
              },
            ],
          }
        : fetchBase(String(input)),
    ),
  );
  mount();
  nav("Knowledge");
  fireEvent.click(await screen.findByText("Vacaciones.txt"));
  await screen.findByText("Pasaje verificable y completo");
  expect(screen.getByRole("dialog")).toHaveTextContent("Vacaciones.txt");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
test("canceling reindex confirmation sends no mutation", async () => {
  const fetcher = mockBase();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  mount();
  nav("Knowledge");
  await screen.findByText("Vacaciones.txt");
  fireEvent.click(screen.getAllByText("Reindexar")[0]);
  expect(fetcher.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
    false,
  );
});
test("activity omits private prompts and arbitrary details", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input) === "/api/activity"
        ? [
            {
              id: 1,
              type: "action.executed",
              actor: "demo@test.local",
              created_at: "2026-10-20T12:00:00Z",
              details: {
                ticket_id: 7,
                prompt: "SECRET-PROMPT",
                api_key: "SECRET-KEY",
              },
            },
          ]
        : fetchBase(String(input)),
    ),
  );
  mount();
  nav("Actividad");
  await screen.findByText("Acción ejecutada");
  expect(
    screen.getByText("Confirmación humana verificada"),
  ).toBeInTheDocument();
  expect(screen.queryByText(/SECRET/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Filtrar actividad"), {
    target: { value: "document." },
  });
  expect(screen.getByText("Registro sin eventos")).toBeInTheDocument();
});
test("untrusted document HTML and code remain literal text", () => {
  const { container } = render(
    <AnswerText
      text={
        "<img src=x onerror=alert(1)> [1]\n```html\n<script>private()</script>\n```"
      }
      sources={[
        {
          chunk_id: 1,
          filename: "doc",
          page: null,
          excerpt: "Evidence",
          score: 0.8,
        },
      ]}
      onSource={() => {}}
    />,
  );
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText(/<script>/)).toBeInTheDocument();
  expect(screen.getByLabelText("Abrir fuente 1")).toBeInTheDocument();
});
test("inspector traps focus and returns to trigger when closed", () => {
  const close = vi.fn();
  const button = document.createElement("button");
  document.body.appendChild(button);
  button.focus();
  const { unmount } = render(
    <Inspector title="Evidence" onClose={close}>
      <button>Inside</button>
    </Inspector>,
  );
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveFocus();
  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(screen.getByText("Inside")).toHaveFocus();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
  unmount();
  expect(button).toHaveFocus();
  button.remove();
});
test("missing provider error preserves the draft for retry", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input).includes("/stream")
      ? Response.json(
          {
            detail:
              "Gemini seleccionado: configura GEMINI_API_KEY solo en el servidor.",
          },
          { status: 503 },
        )
      : Response.json(fetchBase(String(input))),
  );
  mount();
  nav("Copilot");
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Consulta concreta" },
  });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByText("Recuperar mensaje para reintentar"));
  expect(screen.getByLabelText("Mensaje al copiloto")).toHaveValue(
    "Consulta concreta",
  );
});
test("stop query aborts the stream and restores usable composer", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) =>
      String(input).includes("/stream")
        ? new Promise<Response>((_resolve, reject) =>
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("Stopped", "AbortError")),
            ),
          )
        : Response.json(fetchBase(String(input))),
    );
  mount();
  nav("Copilot");
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), {
    target: { value: "Consulta" },
  });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  fireEvent.click(await screen.findByText("Detener consulta"));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Consulta detenida"),
  );
  expect(screen.getByLabelText("Activar micrófono")).toBeEnabled();
  expect(
    fetcher.mock.calls.some(([url]) => String(url).includes("/decision")),
  ).toBe(false);
});
test("workspace change forwards only the selected workspace id", async () => {
  mockBase();
  const select = vi.fn(async () => {});
  render(
    <Copilot
      account={account}
      onSignOut={async () => {}}
      onWorkspace={select}
    />,
  );
  fireEvent.change(screen.getByLabelText("Workspace"), {
    target: { value: "two" },
  });
  expect(select).toHaveBeenCalledWith("two");
});
test("approvals view rejection is explicit and never becomes executed", async () => {
  const action = {
    id: "proposal",
    name: "create_ticket",
    status: "PENDING",
    payload: {
      title: "Validar acceso",
      description: "Alcance limitado",
      priority: "LOW",
    },
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
    Response.json(
      init?.method === "POST"
        ? { status: "rejected" }
        : String(input) === "/api/actions"
          ? [action]
          : fetchBase(String(input)),
    ),
  );
  mount();
  nav("Aprobaciones");
  await screen.findByText("Validar acceso");
  expect(
    screen.getByText("PROPUESTA · TODAVÍA NO EJECUTADA"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByText("Rechazar"));
  await waitFor(() =>
    expect(screen.queryByText("Validar acceso")).not.toBeInTheDocument(),
  );
  nav("Copilot");
  expect(
    screen.getByText("Acción rechazada. No se ejecutó."),
  ).toBeInTheDocument();
});

test("creating a workspace reuses the authenticated endpoint and switches to it", async () => {
  const select = vi.fn(async () => {});
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) =>
      Response.json(
        String(input) === "/api/auth/workspaces" && init?.method === "POST"
          ? { id: "new", name: "Nuevo equipo" }
          : fetchBase(String(input)),
      ),
    );
  render(
    <Copilot
      account={account}
      onSignOut={async () => {}}
      onWorkspace={select}
    />,
  );
  nav("Configuración");
  fireEvent.change(await screen.findByLabelText("Nombre del nuevo workspace"), {
    target: { value: "Nuevo equipo" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Crear workspace" }));
  await waitFor(() => expect(select).toHaveBeenCalledWith("new"));
  expect(
    fetcher.mock.calls.some(
      ([url, init]) =>
        String(url) === "/api/auth/workspaces" &&
        JSON.parse(String(init?.body)).name === "Nuevo equipo",
    ),
  ).toBe(true);
});

test("a failed configuration endpoint does not discard loaded documents", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/system"
      ? Response.json(
          { detail: "Configuración no disponible" },
          { status: 503 },
        )
      : Response.json(fetchBase(String(input))),
  );
  mount();
  await screen.findByText("Vacaciones.txt");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Configuración no disponible",
  );
});

test("loading history from Knowledge never claims document indexing", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/conversations"
      ? Response.json([{ id: "history", title: "Historial pendiente" }])
      : String(input) === "/api/conversations/history"
        ? new Promise<Response>(() => {})
        : Response.json(fetchBase(String(input))),
  );
  mount();
  nav("Knowledge");
  fireEvent.click(await screen.findByText("Historial pendiente"));
  expect(screen.getByText("Añade contexto a tu equipo")).toBeInTheDocument();
  expect(screen.queryByText("Procesando documento…")).not.toBeInTheDocument();
});

test("a failed document inspector explains the absence of chunks", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input).includes("/chunks")
        ? { filename: "Sin-texto.pdf", offset: 0, total: 0, chunks: [] }
        : fetchBase(String(input)),
    ),
  );
  mount();
  nav("Knowledge");
  fireEvent.click(await screen.findByText("Sin-texto.pdf"));
  await screen.findByText("Sin fragmentos conservados");
  expect(screen.queryByText("Siguiente")).not.toBeInTheDocument();
});
