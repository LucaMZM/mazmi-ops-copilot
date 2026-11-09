"use client";
import { useMemo, useState } from "react";
import { FileText, Search, Upload } from "lucide-react";
import { Badge, EmptyState, Spinner } from "../product-ui";
import type { DocumentItem, SystemInfo } from "../product-types";
import { compatible, date, plural } from "@/lib/format";

export function DocBadge({ doc, system }: { doc: DocumentItem; system: SystemInfo | null }) {
  const match = compatible(doc, system);
  return (
    <Badge
      state={doc.status !== "ready" ? doc.status : match === false ? "incompatible" : "ready"}
    >
      {doc.status === "failed"
        ? "Indexación fallida"
        : doc.status !== "ready"
          ? "Procesando"
          : match === false
            ? "Requiere reindexación"
            : match === null
              ? "Indexado, compatibilidad sin verificar"
              : "Disponible para RAG"}
    </Badge>
  );
}

const FILTERS = [
  ["all", "Todos los estados"],
  ["ready", "Indexados"],
  ["processing", "Procesando"],
  ["failed", "Fallidos"],
  ["incompatible", "Incompatibles"],
] as const;

export function KnowledgeView({
  docs,
  system,
  busy,
  onUpload,
  onRemove,
  onReindex,
  onInspect,
  operation,
  processing,
}: {
  docs: DocumentItem[];
  system: SystemInfo | null;
  busy: boolean;
  onUpload: () => void;
  onRemove: (id: string) => void;
  onReindex: (id: string) => void;
  onInspect: (doc: DocumentItem) => void;
  operation: string;
  processing: boolean;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(
    () =>
      docs.filter(
        (d) =>
          d.filename.toLowerCase().includes(query.toLowerCase()) &&
          (filter === "all" ||
            (filter === "incompatible" && compatible(d, system) === false) ||
            filter === d.status),
      ),
    [docs, query, filter, system],
  );
  const ready = docs.filter((d) => d.status === "ready" && compatible(d, system) !== false).length;
  return (
    <div className="pageSection">
      <header className="pageIntro">
        <div>
          <h2>Biblioteca del workspace</h2>
          <p>
            {plural(docs.length, "documento", "documentos")}, {ready} disponibles para responder.
            Se conserva el texto extraído y sus fragmentos, no el archivo original.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={onUpload}>
          <Upload size={17} aria-hidden="true" /> Subir documento
        </button>
      </header>
      <button
        className={`uploadZone surface ${processing ? "processing" : ""}`}
        disabled={busy}
        onClick={onUpload}
      >
        {processing ? <Spinner /> : <Upload size={22} aria-hidden="true" />}
        <span>
          <strong>{processing ? operation || "Procesando documento…" : "Añade contexto a tu equipo"}</strong>
          <small>PDF con texto seleccionable, DOCX, TXT o Markdown, hasta 20 MB</small>
        </span>
      </button>
      {processing && (
        <p className="operationStatus" role="status">
          Extrayendo texto, dividiéndolo por secciones y calculando embeddings. No hay porcentaje
          estimado: el estado cambia al completar o fallar.
        </p>
      )}
      <div className="tableToolbar">
        <label className="searchField">
          <Search size={16} aria-hidden="true" />
          <input
            aria-label="Buscar documentos"
            placeholder="Buscar por nombre"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select aria-label="Filtrar documentos" value={filter} onChange={(e) => setFilter(e.target.value)}>
          {FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <span className="toolbarCount">{plural(filtered.length, "documento", "documentos")}</span>
      </div>
      {filtered.length ? (
        <ul className="documentTable surface">
          {filtered.map((d) => (
            <li className="documentRow" key={d.id}>
              <div className="documentIdentity">
                <div className="fileIcon" aria-hidden="true">
                  <FileText size={19} />
                </div>
                <div>
                  <button className="documentTitle" onClick={() => onInspect(d)}>
                    {d.filename}
                  </button>
                  <p>
                    {plural(d.chunks, "fragmento", "fragmentos")}, {Math.max(1, Math.ceil(d.size_bytes / 1024))} KB,{" "}
                    <time dateTime={d.created_at}>{date(d.created_at)}</time>
                  </p>
                  <code translate="no">
                    {d.embedding_model ?? "Modelo no registrado"}
                    {d.embedding_dimensions ? `, ${d.embedding_dimensions}d` : ""}
                  </code>
                </div>
              </div>
              <div className="documentState">
                <DocBadge doc={d} system={system} />
                {d.error && <p className="documentError">{d.error}</p>}
              </div>
              <div className="rowActions">
                <button className="ghost small" disabled={busy || d.chunks === 0} onClick={() => onInspect(d)}>
                  Fragmentos
                </button>
                <button
                  className="ghost small"
                  disabled={busy}
                  onClick={() => onReindex(d.id)}
                  title="Regenera los embeddings con el modelo activo, conservando el texto"
                >
                  Reindexar
                </button>
                <button className="ghost small danger" disabled={busy} onClick={() => onRemove(d.id)}>
                  Eliminar
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title={docs.length ? "Sin coincidencias" : "Tu biblioteca empieza aquí"}>
          {docs.length
            ? "Cambia la búsqueda o el filtro para encontrar un documento."
            : "Sube una política, un procedimiento o una guía. El copiloto responderá citando sus fragmentos."}
        </EmptyState>
      )}
      <p className="footnote">
        Un documento de otra colección de embeddings queda fuera de la búsqueda vectorial y de
        texto hasta que lo reindexas.
      </p>
    </div>
  );
}
