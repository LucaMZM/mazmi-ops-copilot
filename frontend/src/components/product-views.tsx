"use client";
import { useState } from "react";
import {
  ArrowUpRight,
  Search,
  Upload,
  FileText,
  ArrowRight,
  RefreshCw,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { ActionCard, Badge, EmptyState } from "./product-ui";
import type {
  Activity,
  DocumentItem,
  PendingAction,
  SystemInfo,
  View,
} from "./product-types";

export const eventNames: Record<string, string> = {
  "document.indexed": "Documento indexado",
  "document.reindexed": "Documento reindexado",
  "document.failed": "Indexación fallida",
  "document.deleted": "Documento eliminado",
  "chat.completed": "Consulta completada",
  "action.proposed": "Aprobación solicitada",
  "action.executed": "Acción ejecutada",
  "action.rejected": "Acción rechazada",
  "tool.completed": "Herramienta consultada",
};
export const date = (value: string) =>
  new Date(value).toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
export function compatible(
  d: DocumentItem,
  system: SystemInfo | null,
): boolean | null {
  return system?.embeddings.collection
    ? d.embedding_collection === system.embeddings.collection
    : null;
}
export function DocBadge({
  doc,
  system,
}: {
  doc: DocumentItem;
  system: SystemInfo | null;
}) {
  const match = compatible(doc, system);
  return (
    <Badge
      state={
        doc.status !== "ready"
          ? doc.status
          : match === false
            ? "incompatible"
            : "ready"
      }
    >
      {doc.status === "failed"
        ? "Indexación fallida"
        : doc.status !== "ready"
          ? "Procesando"
          : match === false
            ? "Requiere reindexación"
            : match === null
              ? "Indexado · compatibilidad sin verificar"
              : "Disponible para RAG"}
    </Badge>
  );
}

export function WorkspaceView({
  name,
  docs,
  actions,
  activity,
  system,
  onView,
  onPrompt,
}: {
  name: string;
  docs: DocumentItem[];
  actions: PendingAction[];
  activity: Activity[];
  system: SystemInfo | null;
  onView: (v: View) => void;
  onPrompt: (text: string) => void;
}) {
  const pending = actions.filter((a) => a.status === "PENDING");
  const available = docs.filter(
    (d) => d.status === "ready" && compatible(d, system) !== false,
  );
  return (
    <div className="workspacePage">
      <section className="workspaceIntro">
        <div className="eyebrow">TU ESPACIO DE OPERACIONES</div>
        <h2>
          El contexto para
          <br />
          decidir mejor<span>.</span>
        </h2>
        <p>
          El conocimiento de <strong>{name}</strong>, conectado con las
          decisiones de tu equipo. Cada respuesta con evidencia. Cada acción
          bajo tu control.
        </p>
        <button className="primary" onClick={() => onView("Copilot")}>
          Abrir una consulta <ArrowUpRight size={17} />
        </button>
      </section>
      <div className="workspaceGrid">
        <section className="editorialSection">
          <div className="sectionHeading">
            <h3>Conocimiento disponible</h3>
            <button onClick={() => onView("Knowledge")}>
              Ver documentos <ArrowRight size={15} />
            </button>
          </div>
          {available.length ? (
            available.slice(0, 3).map((d) => (
              <button
                className="documentLink"
                key={d.id}
                onClick={() => onView("Knowledge")}
              >
                <FileText size={20} />
                <span>
                  <strong>{d.filename}</strong>
                  <small>
                    {d.chunks} {d.chunks === 1 ? "fragmento" : "fragmentos"} ·{" "}
                    {d.embedding_model}
                  </small>
                </span>
                <DocBadge doc={d} system={system} />
              </button>
            ))
          ) : (
            <p className="muted">
              Aún no hay documentos compatibles listos. Revisa Knowledge o sube
              conocimiento de tu equipo.
            </p>
          )}
          <div className="suggestedPrompts">
            <span className="eyebrow">UNA PREGUNTA PARA EMPEZAR</span>
            <button
              onClick={() => onPrompt("¿Qué información hay sobre el acceso?")}
            >
              ¿Qué información hay sobre el acceso? <ArrowUpRight size={17} />
            </button>
          </div>
        </section>
        <section className="attentionSection">
          <span className="eyebrow">REQUIERE TU ATENCIÓN</span>
          <h3>
            {pending.length
              ? `${pending.length} propuesta${pending.length > 1 ? "s" : ""} por revisar`
              : "Decisiones al día"}
          </h3>
          <p>
            {pending.length
              ? "Ninguna propuesta se ejecuta hasta que la apruebas. Revisa el alcance antes de decidir."
              : "Las acciones que solicites en modo DO aparecerán aquí para tu aprobación."}
          </p>
          <button onClick={() => onView("Approvals")}>
            Revisar aprobaciones <ArrowRight size={16} />
          </button>
        </section>
      </div>
      <section className="editorialSection">
        <div className="sectionHeading">
          <h3>Lo último en este workspace</h3>
          <button onClick={() => onView("Activity")}>
            Abrir registro <ArrowRight size={15} />
          </button>
        </div>
        {activity.slice(0, 4).map((a) => (
          <div className="activityLine" key={a.id}>
            <span
              className={`eventDot ${a.type.includes("executed") ? "success" : ""}`}
            />
            <strong>{eventNames[a.type] ?? "Evento del workspace"}</strong>
            <span>{a.actor}</span>
            <time>{date(a.created_at)}</time>
          </div>
        ))}
        {!activity.length && (
          <p className="muted">
            La actividad aparecerá al subir documentos o iniciar consultas.
          </p>
        )}
      </section>
    </div>
  );
}

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
  const filtered = docs.filter(
    (d) =>
      d.filename.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "incompatible" && compatible(d, system) === false) ||
        filter === d.status),
  );
  return (
    <div className="pageSection">
      <div className="pageIntro">
        <div>
          <span className="eyebrow">BIBLIOTECA DEL WORKSPACE</span>
          <h2>Conocimiento que puedes verificar.</h2>
          <p>
            Texto documental, fragmentos trazables y una colección de embeddings
            compatible.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={onUpload}>
          <Upload size={17} /> Subir documento
        </button>
      </div>
      <button
        className={`uploadZone ${processing ? "processing" : ""}`}
        disabled={busy}
        onClick={onUpload}
      >
        <Upload size={24} />
        <span>
          <strong>
            {processing
              ? operation || "Procesando documento…"
              : "Añade contexto a tu equipo"}
          </strong>
          <small>
            PDF, DOCX, TXT o Markdown · hasta 20 MB · texto seleccionable
          </small>
        </span>
        <span className="uploadAction">
          Seleccionar archivo <ArrowUpRight size={17} />
        </span>
      </button>
      {processing && (
        <p className="operationStatus" role="status">
          El procesamiento es síncrono. El estado se actualizará al completar o
          fallar; no hay un porcentaje estimado.
        </p>
      )}
      <div className="tableToolbar">
        <label className="searchField">
          <Search size={17} />
          <input
            aria-label="Buscar documentos"
            placeholder="Buscar por nombre…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Filtrar documentos"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Todos los estados</option>
          <option value="ready">Indexados</option>
          <option value="processing">Procesando</option>
          <option value="failed">Fallidos</option>
          <option value="incompatible">Incompatibles</option>
        </select>
        <span>{filtered.length} documentos</span>
      </div>
      {filtered.length ? (
        <div className="documentTable">
          {filtered.map((d) => (
            <article className="documentRow" key={d.id}>
              <div className="documentIdentity">
                <div className="fileIcon">
                  <FileText size={21} />
                </div>
                <div>
                  <button
                    className="documentTitle"
                    onClick={() => onInspect(d)}
                  >
                    {d.filename}
                  </button>
                  <p>
                    {d.chunks} {d.chunks === 1 ? "fragmento" : "fragmentos"} ·{" "}
                    {Math.ceil(d.size_bytes / 1024)} KB · {date(d.created_at)}
                  </p>
                  <code>
                    {d.embedding_model ?? "Modelo no registrado"}
                    {d.embedding_dimensions
                      ? ` · ${d.embedding_dimensions}d`
                      : ""}
                  </code>
                </div>
              </div>
              <div className="documentState">
                <DocBadge doc={d} system={system} />
                {d.error && <p className="documentError">{d.error}</p>}
              </div>
              <div className="rowActions">
                <button
                  disabled={busy || d.chunks === 0}
                  onClick={() => onInspect(d)}
                >
                  Fragmentos
                </button>
                <button
                  disabled={busy}
                  onClick={() => onReindex(d.id)}
                  title="Regenera embeddings conservando el texto"
                >
                  Reindexar
                </button>
                <button
                  className="dangerText"
                  disabled={busy}
                  onClick={() => onRemove(d.id)}
                >
                  Eliminar
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            docs.length ? "Sin coincidencias" : "Tu biblioteca empieza aquí"
          }
        >
          {docs.length
            ? "Cambia la búsqueda o el filtro para encontrar un documento."
            : "Sube una política, un procedimiento o una guía. El copiloto responderá a partir de sus fragmentos."}
        </EmptyState>
      )}
      <p className="footnote">
        Se conserva el texto extraído, no el archivo original. Una colección
        incompatible queda fuera de ambas búsquedas hasta reindexar.
      </p>
    </div>
  );
}

export function ApprovalsView({
  actions,
  busy,
  onDecide,
  onConversation,
}: {
  actions: PendingAction[];
  busy: boolean;
  onDecide: (a: PendingAction, yes: boolean) => void;
  onConversation: (id: string) => void;
}) {
  const [filter, setFilter] = useState("PENDING");
  const filtered = actions.filter(
    (a) => filter === "ALL" || a.status === filter,
  );
  return (
    <div className="pageSection">
      <div className="pageIntro">
        <div>
          <span className="eyebrow">HUMANO EN EL BUCLE</span>
          <h2>Tú autorizas. El sistema registra.</h2>
          <p>
            Solo puedes resolver tus propias propuestas del workspace actual.
          </p>
        </div>
        <ShieldCheck size={32} />
      </div>
      <div className="tabBar" aria-label="Filtrar aprobaciones">
        {[
          ["PENDING", "Pendientes"],
          ["EXECUTED", "Ejecutadas"],
          ["REJECTED", "Rechazadas"],
          ["ALL", "Todas"],
        ].map(([value, label]) => (
          <button
            key={value}
            aria-pressed={filter === value}
            className={filter === value ? "active" : ""}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {filtered.map((a) => (
        <div key={a.id} className="approvalEntry">
          {a.status === "PENDING" ? (
            <ActionCard action={a} busy={busy} onDecide={onDecide} />
          ) : (
            <div className="resolvedAction">
              <Badge state={a.status === "EXECUTED" ? "ready" : "neutral"}>
                {a.status === "EXECUTED"
                  ? "Ejecutada tras aprobación"
                  : "Rechazada · sin ejecución"}
              </Badge>
              <h3>{a.payload.title}</h3>
              <p>{a.payload.description}</p>
            </div>
          )}
          {a.conversation_id && (
            <button
              className="textButton"
              onClick={() => onConversation(a.conversation_id!)}
            >
              Abrir conversación <ArrowUpRight size={14} />
            </button>
          )}
        </div>
      ))}
      {!filtered.length && (
        <EmptyState title="No hay propuestas en este estado">
          Solicita explícitamente una acción en DO para preparar una propuesta.
          La ejecución siempre requiere tu confirmación.
        </EmptyState>
      )}
    </div>
  );
}

export function ActivityView({
  events,
  onRefresh,
}: {
  events: Activity[];
  onRefresh: () => void;
}) {
  const [filter, setFilter] = useState("all");
  const filtered = events.filter(
    (e) => filter === "all" || e.type.startsWith(filter),
  );
  return (
    <div className="pageSection">
      <div className="pageIntro">
        <div>
          <span className="eyebrow">REGISTRO DE DECISIONES</span>
          <h2>Cada paso deja una huella.</h2>
          <p>
            Últimos 50 eventos de este workspace. Actores, decisiones y
            resultados verificables.
          </p>
        </div>
        <button onClick={onRefresh}>
          <RefreshCw size={16} /> Actualizar actividad
        </button>
      </div>
      <div className="tableToolbar">
        <select
          aria-label="Filtrar actividad"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Toda la actividad</option>
          <option value="action.">Aprobaciones y acciones</option>
          <option value="document.">Documentos</option>
          <option value="chat.">Consultas</option>
          <option value="tool.">Herramientas</option>
        </select>
        <span>{filtered.length} eventos</span>
      </div>
      <div className="auditList">
        {filtered.map((a) => (
          <article key={a.id}>
            <div
              className={`auditIcon ${a.type.includes("failed") ? "failed" : ""}`}
            >
              <ShieldCheck size={18} />
            </div>
            <div>
              <div className="auditHeading">
                <h3>{eventNames[a.type] ?? a.type}</h3>
                <time>{date(a.created_at)}</time>
              </div>
              <p>
                {a.actor}
                {a.duration_ms != null ? ` · ${a.duration_ms} ms` : ""}
              </p>
              <div className="auditFacts">
                {typeof a.details.mode === "string" && (
                  <Badge state="neutral">Modo {a.details.mode}</Badge>
                )}
                {typeof a.details.generation_provider === "string" && (
                  <Badge state="neutral">{a.details.generation_provider}</Badge>
                )}
                {a.type === "action.executed" && (
                  <Badge state="ready">Confirmación humana verificada</Badge>
                )}
                {a.type === "action.proposed" && (
                  <Badge state="incompatible">Sin ejecutar</Badge>
                )}
                {typeof a.details.filename === "string" && (
                  <span>{a.details.filename}</span>
                )}
                {typeof a.details.ticket_id === "number" && (
                  <span>Ticket #{a.details.ticket_id}</span>
                )}
                {typeof a.details.abstention_reason === "string" && (
                  <span>Abstención: {a.details.abstention_reason}</span>
                )}
              </div>
              <details>
                <summary>Detalles técnicos permitidos</summary>
                <dl className="eventDetails">
                  {[
                    "model",
                    "retrieved_chunks",
                    "retrieval_ms",
                    "evidence_policy",
                    "abstention_reason",
                    "action_id",
                    "document_id",
                  ].map(
                    (k) =>
                      a.details[k] != null && (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{String(a.details[k])}</dd>
                        </div>
                      ),
                  )}
                </dl>
                <p className="footnote">
                  Los argumentos privados y cuerpos de documentos no se muestran
                  en este registro resumido.
                </p>
              </details>
            </div>
          </article>
        ))}
      </div>
      {!filtered.length && (
        <EmptyState title="Registro sin eventos">
          Prueba otro filtro o inicia una consulta para registrar actividad.
        </EmptyState>
      )}
    </div>
  );
}

export function SettingsView({
  system,
  workspace,
  onReload,
  onCreate,
  creating,
}: {
  system: SystemInfo | null;
  workspace: string;
  onReload: () => void;
  onCreate: (name: string) => Promise<void>;
  creating: boolean;
}) {
  return (
    <div className="pageSection settingsPage">
      <div className="pageIntro">
        <div>
          <span className="eyebrow">CONFIGURACIÓN EFECTIVA DEL SERVIDOR</span>
          <h2>Claridad sobre cada conexión.</h2>
          <p>
            Valores de solo lectura. Cambia el archivo .env local y reinicia el
            backend para aplicarlos.
          </p>
        </div>
        <button onClick={onReload}>
          <RefreshCw size={16} /> Actualizar estado
        </button>
      </div>
      {!system ? (
        <EmptyState title="Configuración no disponible">
          Comprueba la conexión con el backend y vuelve a cargar el estado.
        </EmptyState>
      ) : (
        <>
          <div className="settingsNotice">
            <Settings2 size={21} />
            <p>
              {system.demo
                ? "Modo demo: respuestas y vectores deterministas simulados. Ninguna conexión con Gemini."
                : "Configurado no significa conectado. Esta vista no realiza peticiones al proveedor ni certifica una conexión real."}
            </p>
          </div>
          {[
            ["Generación", system.generation],
            ["Embeddings", system.embeddings],
          ].map(([title, p]) => {
            const provider = p as SystemInfo["generation"];
            return (
              <section className="settingSection" key={String(title)}>
                <div>
                  <h3>{String(title)}</h3>
                  <p>
                    {title === "Generación"
                      ? "Suficiencia documental y propuestas de herramientas."
                      : "Cambiar modelo o dimensión exige reindexar los documentos."}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Proveedor</dt>
                    <dd>{provider.provider}</dd>
                  </div>
                  <div>
                    <dt>Modelo</dt>
                    <dd>
                      <code>{provider.model}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Configuración</dt>
                    <dd>
                      <Badge
                        state={
                          provider.state === "not_configured"
                            ? "failed"
                            : "neutral"
                        }
                      >
                        {provider.state === "demo"
                          ? "Simulación de desarrollo"
                          : provider.state === "configured"
                            ? "Configurado"
                            : "No configurado"}
                      </Badge>
                    </dd>
                  </div>
                  <div>
                    <dt>Conexión real</dt>
                    <dd>
                      {provider.verification === "simulated"
                        ? "Probado con fixtures; sin conexión real"
                        : "No verificada"}
                    </dd>
                  </div>
                </dl>
              </section>
            );
          })}
          <section className="settingSection">
            <div>
              <h3>Indexación y colecciones</h3>
              <p>
                Búsqueda híbrida, filtros de workspace y colección en ambas
                ramas.
              </p>
            </div>
            <dl>
              <div>
                <dt>Dimensiones</dt>
                <dd>{system.embeddings.dimensions}</dd>
              </div>
              <div>
                <dt>Colección activa</dt>
                <dd>
                  <code>
                    {system.embeddings.collection ??
                      "Pendiente de verificar el digest Ollama"}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Formato / tamaño</dt>
                <dd>PDF, DOCX, TXT, MD / {system.indexing.max_file_mb} MB</dd>
              </div>
              <div>
                <dt>Estrategia</dt>
                <dd>Vector + FTS · RRF · K={system.indexing.top_k}</dd>
              </div>
            </dl>
          </section>
          <section className="settingSection">
            <div>
              <h3>Voz opcional</h3>
              <p>
                El chat de texto está disponible sin micrófono ni modelos de
                audio.
              </p>
            </div>
            <dl>
              <div>
                <dt>Dictado · {system.voice.stt}</dt>
                <dd>
                  {system.voice.stt_configured
                    ? "Ruta local configurada; ejecución no verificada"
                    : "No configurado"}
                </dd>
              </div>
              <div>
                <dt>Salida · {system.voice.tts}</dt>
                <dd>
                  {system.voice.tts_configured
                    ? "Configurado; ejecución no verificada"
                    : "No configurado"}
                </dd>
              </div>
            </dl>
          </section>
          <section className="settingSection">
            <div>
              <h3>Workspace</h3>
              <p>
                Los datos y las aprobaciones dependen de tu membresía
                verificada.
              </p>
            </div>
            <div>
              <p>{workspace}</p>
              <form
                className="workspaceCreate"
                onSubmit={(e) => {
                  e.preventDefault();
                  const name = String(
                    new FormData(e.currentTarget).get("name") ?? "",
                  ).trim();
                  if (name) void onCreate(name);
                }}
              >
                <label>
                  Crear otro workspace
                  <input
                    aria-label="Nombre del nuevo workspace"
                    name="name"
                    required
                    maxLength={100}
                    placeholder="Nombre del equipo"
                  />
                </label>
                <button disabled={creating}>
                  {creating ? "Creando…" : "Crear workspace"}
                </button>
              </form>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
