"use client";
import { useEffect, useState } from "react";
import {
  Bot,
  Database,
  FileStack,
  Layers,
  MessageSquareText,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import { Inspector, Spinner } from "../product-ui";
import type { Source, TurnDiagnostics } from "../product-types";
import { errorMessage, request } from "@/lib/api";

type Props = {
  conversationId: string;
  sources: Source[];
  /** Which of the conversation's turns with these same sources this answer is (0-based). */
  occurrence: number;
  onClose: () => void;
};

const NS_PER_MS = 1_000_000;
const REASONS: Record<string, string> = {
  insufficient_evidence: "evidencia insuficiente",
  conflicting_evidence: "evidencia en conflicto",
  no_retrieval_evidence: "sin fragmentos recuperados",
  incomplete_evidence_assessment: "comprobación incompleta",
  invalid_evidence_assessment: "comprobación no válida",
  invalid_evidence_selection: "selección no válida",
};

const ms = (value: number | null | undefined) =>
  value == null ? "—" : value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
const num = (value: number | null | undefined, digits = 0) =>
  value == null ? "—" : value.toLocaleString("es-ES", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const sameIds = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/** Pick this answer's record: same retrieved chunks, in conversation order. */
export function matchTurn(turns: TurnDiagnostics[], sources: Source[], occurrence: number) {
  const ids = sources.map((s) => s.chunk_id);
  return turns.filter((t) => sameIds(t.source_chunk_ids, ids))[occurrence] ?? null;
}

/**
 * Diagnostic view of one answered turn, from the audit record the server already writes.
 * Only measured values appear; a stage without a measurement shows a dash, never an estimate.
 */
export function RagInspector({ conversationId, sources, occurrence, onClose }: Props) {
  const [state, setState] = useState<{ turn: TurnDiagnostics | null; error: string; busy: boolean }>({
    turn: null,
    error: "",
    busy: true,
  });
  useEffect(() => {
    let alive = true;
    request<TurnDiagnostics[]>(`/api/conversations/${conversationId}/diagnostics`)
      .then((turns) => alive && setState({ turn: matchTurn(turns, sources, occurrence), error: "", busy: false }))
      .catch((err) => alive && setState({ turn: null, error: errorMessage(err), busy: false }));
    return () => {
      alive = false;
    };
  }, [conversationId, sources, occurrence]);

  return (
    <Inspector title="Diagnóstico RAG" subtitle="Valores medidos por el servidor en esta respuesta" onClose={onClose}>
      {state.busy ? (
        <p role="status" className="streamStatus">
          <Spinner /> Leyendo el registro de la respuesta…
        </p>
      ) : state.error ? (
        <p role="alert" className="errorText">
          {state.error}
        </p>
      ) : !state.turn ? (
        <p className="footnote">
          No hay registro de diagnóstico para esta respuesta. Las respuestas anteriores a esta
          versión o las que no consultaron documentos no lo tienen.
        </p>
      ) : (
        <Pipeline turn={state.turn} sources={sources} />
      )}
    </Inspector>
  );
}

function Pipeline({ turn, sources }: { turn: TurnDiagnostics; sources: Source[] }) {
  const r = turn.retrieval;
  const byId = new Map(sources.map((s, i) => [s.chunk_id, { source: s, number: i + 1 }]));
  const calls = turn.model_calls_detail;
  const loads = calls.reduce((sum, c) => sum + (typeof c.load_duration === "number" ? c.load_duration : 0), 0);
  const generation = calls.reduce(
    (sum, c) => sum + (typeof c.total_duration === "number" ? c.total_duration : 0),
    0,
  );
  const reason = turn.abstention_reason;
  const stages: { icon: LucideIcon; title: string; value: string; detail: React.ReactNode }[] = [
    {
      icon: MessageSquareText,
      title: "Consulta",
      value: turn.mode ?? "—",
      detail: <>Modo {turn.mode ?? "desconocido"}. El texto de la pregunta no se guarda en este registro.</>,
    },
    {
      icon: Database,
      title: "Recuperación",
      value: ms(turn.retrieval_ms),
      detail: (
        <dl className="stageFacts">
          <Fact label="Embedding de la consulta" value={ms(r.embedding_ms)} />
          <Fact label="Búsqueda SQL" value={ms(r.duration_ms)} />
          <Fact label="Candidatos vectoriales" value={num(r.vector_candidates)} />
          <Fact label="Candidatos léxicos" value={num(r.lexical_candidates)} />
          <Fact label="Únicos tras fusión" value={num(r.unique_candidates)} />
          <Fact label="Estrategia" value={r.strategy ?? "—"} mono />
        </dl>
      ),
    },
    {
      icon: FileStack,
      title: "Fragmentos",
      value: `${num(turn.retrieved_chunks)} seleccionados`,
      detail: (
        <div className="tableScroll">
        <table className="chunkTable">
          <thead>
            <tr>
              <th scope="col">Fuente</th>
              <th scope="col">Similitud</th>
              <th scope="col">RRF</th>
              <th scope="col" title="Rango en la búsqueda vectorial">Vect.</th>
              <th scope="col" title="Rango en la búsqueda léxica">Léx.</th>
            </tr>
          </thead>
          <tbody>
            {r.selected.map((item, i) => {
              const known = item.chunk_id != null ? byId.get(item.chunk_id) : undefined;
              return (
                <tr key={item.chunk_id ?? i} className={turn.citations.includes(known?.number ?? -1) ? "cited" : ""}>
                  <th scope="row">
                    {known ? `${known.number}. ${known.source.filename}` : `#${item.chunk_id ?? "?"}`}
                  </th>
                  <td>{num(item.score, 3)}</td>
                  <td>{num(item.rrf_score, 4)}</td>
                  <td>{item.vector_rank ?? "—"}</td>
                  <td>{item.lexical_rank ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      ),
    },
    {
      icon: Layers,
      title: "Contexto",
      value: turn.evidence_policy ?? "—",
      detail: (
        <dl className="stageFacts">
          <Fact label="Política de evidencia" value={turn.evidence_policy ?? "—"} mono />
          <Fact label="Documentos sustituidos ignorados" value={num(turn.superseded_ignored.length)} />
          <Fact label="Colección de embeddings" value={r.embedding_collection ?? "—"} mono />
        </dl>
      ),
    },
    {
      icon: Bot,
      title: "LLM",
      value: turn.model ?? "Sin modelo",
      detail: (
        <dl className="stageFacts">
          <Fact label="Llamadas al modelo" value={num(turn.model_calls)} />
          <Fact label="Tokens de entrada" value={num(turn.input_tokens)} />
          <Fact label="Tokens de salida" value={num(turn.output_tokens)} />
          <Fact label="Tiempo en Ollama" value={calls.length ? ms(generation / NS_PER_MS) : "—"} />
          <Fact label="Carga del modelo" value={calls.length ? ms(loads / NS_PER_MS) : "—"} />
          {typeof turn.assessment.attempts === "number" && (
            <Fact label="Intentos de cita" value={num(turn.assessment.attempts)} />
          )}
        </dl>
      ),
    },
    {
      icon: ScrollText,
      title: "Respuesta",
      value: reason ? "Abstención" : `${turn.citations.length} ${turn.citations.length === 1 ? "cita" : "citas"}`,
      detail: (
        <dl className="stageFacts">
          <Fact label="Resultado" value={reason ? `Se abstuvo: ${REASONS[reason] ?? reason}` : "Respuesta con citas"} />
          <Fact label="Fuentes citadas" value={turn.citations.length ? turn.citations.join(", ") : "—"} />
          {typeof turn.assessment.quotes_verified === "boolean" && (
            <Fact label="Citas verificadas" value={turn.assessment.quotes_verified ? "Sí" : "No"} />
          )}
          <Fact label="Fase de evidencia" value={ms(turn.duration_ms)} />
        </dl>
      ),
    },
  ];
  return (
    <>
      <p className="pipelineTotal">
        <span>Recuperación + evidencia</span>
        <strong>{ms((turn.retrieval_ms ?? 0) + (turn.duration_ms ?? 0))}</strong>
      </p>
      <ol className="pipeline" aria-label="Etapas del pipeline">
        {stages.map(({ icon: Icon, title, value, detail }) => (
          <li key={title} className="pipelineStage">
            <span className="stageNode" aria-hidden="true">
              <Icon size={15} strokeWidth={1.75} />
            </span>
            <details>
              <summary>
                <span className="stageTitle">{title}</span>
                <span className="stageValue">{value}</span>
              </summary>
              <div className="stageDetail">{detail}</div>
            </details>
          </li>
        ))}
      </ol>
      <p className="footnote">
        Los tiempos de Ollama vienen del propio servidor de modelos. Este registro nunca contiene
        el texto de la pregunta, de los documentos ni de la respuesta.
      </p>
    </>
  );
}

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{mono ? <code>{value}</code> : value}</dd>
    </div>
  );
}
