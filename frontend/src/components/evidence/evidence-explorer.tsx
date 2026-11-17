"use client";
import { useEffect, useMemo } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Badge, Inspector } from "../product-ui";
import type { DocumentItem, Source } from "../product-types";
import { quoteRanges, quotesFor, segments } from "./highlight";
import { date } from "@/lib/format";

type Props = {
  /** The answer the sources belong to: its text says which ones were cited and how. */
  answer: string;
  sources: Source[];
  index: number;
  documents: DocumentItem[];
  onIndex: (index: number) => void;
  onClose: () => void;
  onDocument: (source: Source) => void;
};

/**
 * The evidence behind one answer, one source at a time. Everything shown comes from the
 * server: the stored passage, its metadata and the literal quotes the answer displays. The
 * quotes are marked where they literally occur; nothing is paraphrased or inferred.
 */
export function EvidenceExplorer({
  answer,
  sources,
  index,
  documents,
  onIndex,
  onClose,
  onDocument,
}: Props) {
  const source = sources[index];
  const number = index + 1;
  const cited = useMemo(
    () => new Set(Array.from(answer.matchAll(/\[(\d+)\]/g), (m) => Number(m[1]))),
    [answer],
  );
  const parts = useMemo(() => {
    const ranges = quoteRanges(source.excerpt, quotesFor(answer, number));
    return { ranges, segments: segments(source.excerpt, ranges) };
  }, [answer, number, source.excerpt]);
  const document = documents.find((d) => d.id === source.document_id);
  const isCited = cited.has(number);

  // Arrow keys move between sources unless the person is typing somewhere.
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const target = e.target instanceof Element ? e.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (e.key === "ArrowRight" && index < sources.length - 1) onIndex(index + 1);
      if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [index, sources.length, onIndex]);

  return (
    <Inspector
      title={source.filename}
      subtitle={`Fuente ${number} de ${sources.length} de esta respuesta`}
      onClose={onClose}
    >
      <nav className="evidenceNav" aria-label="Fuentes de la respuesta">
        <button
          className="iconButton small"
          aria-label="Fuente anterior"
          disabled={index === 0}
          onClick={() => onIndex(index - 1)}
        >
          <ChevronLeft size={17} />
        </button>
        <div className="evidenceSteps">
          {sources.map((s, i) => (
            <button
              key={s.chunk_id}
              className={`evidenceStep ${i === index ? "active" : ""} ${cited.has(i + 1) ? "cited" : ""}`}
              aria-current={i === index ? "true" : undefined}
              aria-label={`Fuente ${i + 1}: ${s.filename}${cited.has(i + 1) ? ", citada" : ""}`}
              onClick={() => onIndex(i)}
            >
              {i + 1}
            </button>
          ))}
        </div>
        <button
          className="iconButton small"
          aria-label="Fuente siguiente"
          disabled={index === sources.length - 1}
          onClick={() => onIndex(index + 1)}
        >
          <ChevronRight size={17} />
        </button>
      </nav>

      <div className="evidenceBadges">
        <Badge state={isCited ? "ready" : "neutral"}>
          {isCited ? "Citada en la respuesta" : "Recuperada, sin citar"}
        </Badge>
        {source.superseded && <Badge state="incompatible">Documento sustituido</Badge>}
      </div>

      <dl className="evidenceMeta">
        <div>
          <dt>Sección</dt>
          <dd>{source.section ?? "Sin sección"}</dd>
        </div>
        <div>
          <dt>Página</dt>
          <dd>{source.page ?? "Sin paginación fiable"}</dd>
        </div>
        <div>
          <dt>Fragmento</dt>
          <dd>#{source.chunk_id}</dd>
        </div>
        <div>
          <dt>Similitud</dt>
          <dd>{source.score.toFixed(3)}</dd>
        </div>
        {document && (
          <>
            <div>
              <dt>Versión indexada</dt>
              <dd>{date(document.created_at)}</dd>
            </div>
            {document.embedding_model && (
              <div>
                <dt>Embeddings</dt>
                <dd>
                  <code>
                    {document.embedding_model}
                    {document.embedding_dimensions ? `, ${document.embedding_dimensions}d` : ""}
                  </code>
                </dd>
              </div>
            )}
          </>
        )}
      </dl>

      <h3 className="inspectorLabel">Pasaje almacenado completo</h3>
      <blockquote key={source.chunk_id} className="evidencePassage">
        {parts.segments.map((part, i) =>
          part.mark ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>,
        )}
      </blockquote>
      <p className="footnote">
        {parts.ranges.length
          ? "Resaltado: las frases literales que muestra la respuesta, verificadas por el servidor en este pasaje."
          : isCited
            ? "La respuesta cita este pasaje; su cita no aparece aquí carácter a carácter, así que no se resalta nada."
            : "La respuesta no cita este fragmento: se recuperó como contexto."}{" "}
        La similitud mide cercanía, no certeza ni aplicabilidad.
      </p>
      {source.document_id && (
        <button className="ghost" onClick={() => onDocument(source)}>
          Ver todos los fragmentos del documento
        </button>
      )}
    </Inspector>
  );
}
