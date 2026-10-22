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

const ollamaSystem: SystemInfo = {
  ...system,
  generation: {
    provider: "ollama",
    model: "qwen3:4b",
    state: "configured",
    verification: "not_checked",
  },
  embeddings: {
    provider: "ollama",
    model: "embeddinggemma",
    state: "configured",
    verification: "not_checked",
    dimensions: 768,
    collection: null,
  },
};
const checkedOllama: SystemInfo = {
  ...ollamaSystem,
  generation: {
    ...ollamaSystem.generation,
    verification: "passed",
    checked_at: "2026-10-22T12:00:00Z",
  },
  embeddings: {
    ...ollamaSystem.embeddings,
    verification: "passed",
    checked_at: "2026-10-22T12:00:00Z",
    collection: "ollama:embeddinggemma:768:test-digest",
  },
  local_check: {
    status: "passed",
    checked_at: "2026-10-22T12:00:00Z",
    scope: "structured-output-and-embedding-fixtures",
    duration_ms: 100,
    message: "Prueba local completada con texto ficticio.",
  },
};

test("Ollama verification is manual, single-flight and does not block the chat", async () => {
  let complete!: (response: Response) => void;
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/system/check-local"
      ? new Promise<Response>((resolve) => { complete = resolve; })
      : Response.json(String(input) === "/api/system" ? ollamaSystem : fetchBase(String(input))),
  );
  mount();
  nav("Configuración");
  const verify = await screen.findByRole("button", { name: "Verificar Ollama" });
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/check-local"))).toBe(false);
  fireEvent.click(verify);
  fireEvent.click(verify);
  expect(screen.getByRole("button", { name: "Verificando Ollama…" })).toBeDisabled();
  expect(screen.getByText(/Las dos pruebas pueden tardar/)).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/check-local"))).toHaveLength(1);
  expect(fetcher.mock.calls.find(([url]) => String(url).endsWith("/check-local"))?.[1]?.method).toBe("POST");
  nav("Copilot");
  expect(screen.getByLabelText("Mensaje al copiloto")).toBeEnabled();
  expect(screen.getByLabelText("Proveedor de la consulta")).toHaveTextContent("Ollama · seleccionado, sin verificar");
  complete(Response.json(checkedOllama));
  await waitFor(() => expect(screen.getByLabelText("Proveedor de la consulta")).toHaveTextContent("última prueba local completada"));
  expect(screen.getByLabelText("Proveedor de la consulta").querySelector("time")).toHaveAttribute("datetime", "2026-10-22T12:00:00Z");
  expect(screen.queryByText(/Conectado/)).not.toBeInTheDocument();
});

test.each<[string, SystemInfo]>([
  ["Gemini", system],
  ["demo", { ...ollamaSystem, demo: true }],
  ["mixed providers", { ...ollamaSystem, embeddings: system.embeddings }],
])("%s never offers or runs a local Ollama probe", async (_label, config) => {
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(String(input) === "/api/system" ? config : fetchBase(String(input))),
  );
  mount();
  nav("Configuración");
  await screen.findByText(config.generation.model);
  expect(screen.queryByRole("button", { name: "Verificar Ollama" })).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});

test("local verification failures stay actionable and never claim a connection", async () => {
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/system/check-local"
      ? Response.json({ detail: "Ya hay una prueba local en curso." }, { status: 409 })
      : Response.json(String(input) === "/api/system" ? ollamaSystem : fetchBase(String(input))),
  );
  mount();
  nav("Configuración");
  fireEvent.click(await screen.findByRole("button", { name: "Verificar Ollama" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Ya hay una prueba local en curso."));
  expect(screen.getByRole("alert")).toHaveTextContent("actualiza el estado antes de repetir");
  expect(screen.getByRole("button", { name: "Verificar Ollama" })).toBeEnabled();
  expect(screen.getAllByText("No verificada")).toHaveLength(2);
  expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/check-local"))).toHaveLength(1);
});

test("a completed negative fixture check displays failure and no verified collection", async () => {
  const failed: SystemInfo = {
    ...ollamaSystem,
    generation: { ...ollamaSystem.generation, verification: "failed" },
    embeddings: { ...ollamaSystem.embeddings, verification: "failed" },
    local_check: { ...checkedOllama.local_check!, status: "failed", message: "Comprueba el servicio, los modelos y sus dimensiones." },
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(String(input) === "/api/system/check-local" ? failed : String(input) === "/api/system" ? ollamaSystem : fetchBase(String(input))),
  );
  mount();
  nav("Configuración");
  fireEvent.click(await screen.findByRole("button", { name: "Verificar Ollama" }));
  await screen.findByText("Comprueba el servicio, los modelos y sus dimensiones.");
  expect(screen.getAllByText("Última prueba local fallida")).toHaveLength(2);
  expect(screen.getByText("Pendiente de verificar el digest Ollama")).toBeInTheDocument();
  nav("Copilot");
  expect(screen.getByLabelText("Proveedor de la consulta")).toHaveTextContent("Ollama · última prueba local fallida");
});

test("a stale local result cannot overwrite a freshly loaded provider configuration", async () => {
  let complete!: (response: Response) => void;
  let config = ollamaSystem;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/system/check-local"
      ? new Promise<Response>((resolve) => { complete = resolve; })
      : Response.json(String(input) === "/api/system" ? config : fetchBase(String(input))),
  );
  mount();
  nav("Configuración");
  fireEvent.click(await screen.findByRole("button", { name: "Verificar Ollama" }));
  config = system;
  fireEvent.click(screen.getByRole("button", { name: "Actualizar estado" }));
  await screen.findByText("gemini-test");
  complete(Response.json(checkedOllama));
  await waitFor(() => expect(screen.queryByText("qwen3:4b")).not.toBeInTheDocument());
  nav("Copilot");
  expect(screen.getByLabelText("Proveedor de la consulta")).toHaveTextContent("Gemini · sin API key configurada");
});

test("demo chat labels simulation rather than a real local model", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    Response.json(String(input) === "/api/system" ? { ...ollamaSystem, demo: true } : fetchBase(String(input))),
  );
  mount();
  await screen.findByText("DEMO DE DESARROLLO");
  nav("Copilot");
  expect(screen.getByLabelText("Proveedor de la consulta")).toHaveTextContent("DEMO · IA simulada");
  expect(screen.getByLabelText("Proveedor de la consulta")).not.toHaveTextContent("prueba local completada");
});

test("local verification timeout does not retry and explains that the backend may continue", async () => {
  const timeout = new Error("Timed out");
  timeout.name = "TimeoutError";
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input) === "/api/system/check-local") throw timeout;
    return Response.json(String(input) === "/api/system" ? ollamaSystem : fetchBase(String(input)));
  });
  mount();
  nav("Configuración");
  fireEvent.click(await screen.findByRole("button", { name: "Verificar Ollama" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("el backend puede seguir procesándola"));
  expect(screen.getByRole("alert")).toHaveTextContent("Actualiza el estado antes de volver a verificar");
  expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/check-local"))).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Verificar Ollama" })).toBeEnabled();
});
