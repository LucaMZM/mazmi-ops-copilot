import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Copilot } from "../src/components/copilot";
import { quoteRanges, quotesFor, segments } from "../src/components/evidence/highlight";
import { matchTurn } from "../src/components/diagnostics/rag-inspector";
import type { Source, TurnDiagnostics } from "../src/components/product-types";

const account = { email: "me@example.com", workspace_id: "w", workspaces: [{ id: "w", name: "Team" }] };
const ANSWER =
  "Respuesta: 23 días laborables\nSegún vacaciones.md (Vacaciones):\n«Cada persona dispone de 23 días laborables.» [2]";
const SOURCES: Source[] = [
  { chunk_id: 4, document_id: "d1", filename: "manual.md", page: null, excerpt: "Texto de contexto.", score: 0.41, section: "Intro" },
  {
    chunk_id: 9,
    document_id: "d2",
    filename: "vacaciones.md",
    page: 3,
    excerpt: "Política anual. Cada persona dispone de 23 días   laborables. Se pide con antelación.",
    score: 0.82,
    section: "Vacaciones",
  },
];

function sse(...events: unknown[]) {
  const bytes = new TextEncoder().encode(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""));
  return new Response(new ReadableStream({ start: (c) => (c.enqueue(bytes), c.close()) }), {
    headers: { "Content-Type": "text/event-stream" },
  });
}
const turn = (ids: number[], extra: Partial<TurnDiagnostics> = {}): TurnDiagnostics => ({
  created_at: "2026-11-17T10:00:00Z",
  recorded_ms: 900,
  mode: "ASK",
  model: "qwen3:4b",
  generation_provider: "ollama",
  evidence_policy: "extractive_v5_focused",
  abstention_reason: null,
  answer_lead_withheld: null,
  duration_ms: 800,
  retrieval_ms: 120,
  retrieved_chunks: ids.length,
  model_calls: 2,
  input_tokens: 900,
  output_tokens: 60,
  citations: [2],
  source_chunk_ids: ids,
  superseded_ignored: [],
  model_assessment_performed: true,
  retrieval: {
    strategy: "hybrid_rrf_v2",
    lexical_query_mode: "any_terms_v2",
    embedding_collection: "ollama:embeddinggemma:768",
    abstention_reason: null,
    duration_ms: 30,
    embedding_ms: 90,
    vector_candidates: 24,
    lexical_candidates: 5,
    unique_candidates: 26,
    selected: ids.map((id, i) => ({ chunk_id: id, score: 0.5, rrf_score: 0.03, vector_rank: i + 1, lexical_rank: null, lexical_score: null })),
  },
  assessment: { attempts: 1, quotes_verified: true },
  model_calls_detail: [{ total_duration: 700_000_000, load_duration: 50_000_000, eval_count: 40 }],
  tools: [],
  ...extra,
});

function mount(diagnostics: TurnDiagnostics[] = [turn([4, 9])]) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/chat/stream")
      return sse({
        type: "done",
        data: { conversation_id: "c1", answer: ANSWER, sources: SOURCES, pending_action: null },
      });
    if (url === "/api/conversations/c1/diagnostics") return Response.json(diagnostics);
    if (url === "/api/documents")
      return Response.json([
        { id: "d2", filename: "vacaciones.md", pages: 3, chunks: 4, status: "ready", mime_type: "text/markdown", size_bytes: 10, created_at: "2026-11-01T09:00:00Z", error: null, embedding_model: "embeddinggemma", embedding_dimensions: 768 },
      ]);
    return Response.json([]);
  });
  render(<Copilot account={account} onSignOut={async () => {}} onWorkspace={async () => {}} />);
}
async function ask() {
  fireEvent.change(screen.getByLabelText("Mensaje al copiloto"), { target: { value: "¿Vacaciones?" } });
  fireEvent.click(screen.getByLabelText("Enviar mensaje"));
  await screen.findByText(/Cada persona dispone/);
}

test("quotes are found literally in the passage, across spacing, and never guessed", () => {
  expect(quotesFor(ANSWER, 2)).toEqual(["Cada persona dispone de 23 días laborables."]);
  expect(quotesFor(ANSWER, 1)).toEqual([]);
  const passage = SOURCES[1].excerpt;
  const ranges = quoteRanges(passage, quotesFor(ANSWER, 2));
  expect(ranges).toHaveLength(1);
  expect(passage.slice(...ranges[0])).toBe("Cada persona dispone de 23 días   laborables.");
  expect(quoteRanges(passage, ["Esta frase no existe en el pasaje"])).toEqual([]);
  expect(segments("abc", [])).toEqual([{ text: "abc", mark: false }]);
});

test("the evidence explorer opens on the cited source, marks its quote and navigates", async () => {
  mount();
  await ask();
  fireEvent.click(screen.getByLabelText("Abrir fuente 2"));
  const dialog = screen.getByRole("dialog", { name: "vacaciones.md" });
  expect(dialog).toHaveTextContent("Fuente 2 de 2");
  expect(dialog).toHaveTextContent("Citada en la respuesta");
  expect(dialog.querySelector("mark")).toHaveTextContent("Cada persona dispone de 23 días laborables.");
  expect(dialog).toHaveTextContent("Página3");
  await waitFor(() => expect(dialog).toHaveTextContent("embeddinggemma, 768d"));
  fireEvent.click(within(dialog).getByLabelText("Fuente anterior"));
  const first = screen.getByRole("dialog", { name: "manual.md" });
  expect(first).toHaveTextContent("Recuperada, sin citar");
  expect(first.querySelector("mark")).toBeNull();
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(screen.getByRole("dialog", { name: "vacaciones.md" })).toBeInTheDocument();
});

test("diagnostics stay hidden until enabled", async () => {
  window.localStorage.removeItem("mazmi-diagnostics");
  mount();
  await ask();
  expect(screen.queryByRole("button", { name: /Diagnóstico RAG/ })).not.toBeInTheDocument();
});

test("the RAG inspector reads this answer's audit record", async () => {
  window.localStorage.setItem("mazmi-diagnostics", "on");
  mount([turn([1, 2]), turn([4, 9])]);
  await ask();
  fireEvent.click(screen.getByRole("button", { name: /Diagnóstico RAG/ }));
  const dialog = await screen.findByRole("dialog", { name: "Diagnóstico RAG" });
  await within(dialog).findByText("Recuperación + evidencia");
  expect(dialog).toHaveTextContent("920 ms");
  expect(dialog).toHaveTextContent("qwen3:4b");
  expect(dialog).toHaveTextContent("2. vacaciones.md");
  expect(dialog).toHaveTextContent("Candidatos vectoriales24");
  window.localStorage.removeItem("mazmi-diagnostics");
});

test("an answer without a matching record says so instead of inventing numbers", () => {
  expect(matchTurn([turn([1])], SOURCES, 0)).toBeNull();
  expect(matchTurn([turn([4, 9]), turn([4, 9], { duration_ms: 5 })], SOURCES, 1)?.duration_ms).toBe(5);
});

test("⌘K opens a palette that finds sections and runs them with the keyboard", async () => {
  mount();
  fireEvent.keyDown(window, { key: "k", metaKey: true });
  const input = screen.getByRole("combobox", { name: /Buscar secciones/ });
  expect(input).toHaveFocus();
  fireEvent.change(input, { target: { value: "configuracion" } });
  expect(screen.getAllByRole("option")).toHaveLength(1);
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.queryByRole("dialog", { name: "Paleta de comandos" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Configuración");
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});
