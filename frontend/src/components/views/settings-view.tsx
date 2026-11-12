"use client";
import { RefreshCw } from "lucide-react";
import { Badge, EmptyState } from "../product-ui";
import type { ProviderInfo, SystemInfo } from "../product-types";
import { date } from "@/lib/format";
import { useTheme, type ThemePreference } from "@/hooks/use-theme";

export function ProviderContext({ system }: { system: SystemInfo | null }) {
  if (!system) return null;
  const provider = system.generation;
  const label =
    provider.verification === "passed"
      ? "Ollama local · última prueba completada"
      : provider.verification === "failed"
        ? "Ollama local · última prueba fallida"
        : "Ollama local · sin verificar";
  const tone =
    provider.verification === "passed" ? "ok" : provider.verification === "failed" ? "warn" : "neutral";
  return (
    <div className={`providerContext ${tone}`} aria-label="Modelo local de la consulta">
      <span className="providerDot" aria-hidden="true" />
      <span>{label}</span>
      <code translate="no">{provider.model}</code>
      {provider.checked_at && <time dateTime={provider.checked_at}>{date(provider.checked_at)}</time>}
    </div>
  );
}

function verificationText(provider: ProviderInfo) {
  return provider.verification === "passed"
    ? "Última prueba local completada"
    : provider.verification === "failed"
      ? "Última prueba local fallida"
      : "No verificada";
}

function ModelSection({ title, help, provider }: { title: string; help: string; provider: ProviderInfo }) {
  return (
    <section className="settingSection surface">
      <div>
        <h3>{title}</h3>
        <p>{help}</p>
      </div>
      <dl>
        <div>
          <dt>Motor</dt>
          <dd>Ollama (local)</dd>
        </div>
        <div>
          <dt>Modelo</dt>
          <dd>
            <code translate="no">{provider.model}</code>
          </dd>
        </div>
        <div>
          <dt>Estado</dt>
          <dd>
            <Badge state={provider.verification === "failed" ? "failed" : "neutral"}>
              {verificationText(provider)}
            </Badge>
            {provider.checked_at && (
              <>
                <br />
                <small>
                  Comprobado el <time dateTime={provider.checked_at}>{date(provider.checked_at)}</time>
                </small>
              </>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}

const THEMES: [ThemePreference, string][] = [
  ["dark", "Oscuro"],
  ["light", "Claro"],
  ["system", "Sistema"],
];

export function SettingsView({
  system,
  workspace,
  onReload,
  onCreate,
  creating,
  checkingLocal,
  localCheckError,
  onCheckLocal,
}: {
  system: SystemInfo | null;
  workspace: string;
  onReload: () => void;
  onCreate: (name: string) => Promise<void>;
  creating: boolean;
  checkingLocal: boolean;
  localCheckError: string;
  onCheckLocal: () => Promise<void>;
}) {
  const [theme, setTheme] = useTheme();
  return (
    <div className="pageSection settingsPage">
      <header className="pageIntro">
        <div>
          <h2>Configuración efectiva del servidor</h2>
          <p>
            Valores de solo lectura. Para cambiarlos, edita el archivo .env local y reinicia el
            backend. Todo el procesamiento se realiza en tu equipo con Ollama.
          </p>
        </div>
        <button className="ghost" onClick={onReload}>
          <RefreshCw size={16} aria-hidden="true" /> Actualizar estado
        </button>
      </header>
      {!system ? (
        <EmptyState title="Configuración no disponible">
          Comprueba la conexión con el backend y vuelve a cargar el estado.
        </EmptyState>
      ) : (
        <>
          <p className="settingsNotice surface">
            Configurado no significa conectado. Actualizar estado solo lee la configuración; la
            prueba local se ejecuta cuando la solicitas.
          </p>
          <ModelSection
            title="Generación"
            help="Selecciona citas literales, comprueba que responden a la pregunta y propone acciones. Nunca redacta hechos sin pasaje."
            provider={system.generation}
          />
          <ModelSection
            title="Embeddings"
            help="Cambiar de modelo o dimensión exige reindexar los documentos."
            provider={system.embeddings}
          />
          <section className="settingSection surface">
            <div>
              <h3>Motor local</h3>
              <p>
                {system.runtime.reasoning === "off"
                  ? "Razonamiento desactivado: Qwen3 gasta su presupuesto de salida en responder, no en pensar."
                  : "Razonamiento activado: las respuestas son más lentas y pueden agotar el tiempo."}
              </p>
            </div>
            <dl>
              <div>
                <dt>Evidencia</dt>
                <dd>
                  {system.runtime.evidence_mode === "quoted_v6"
                    ? "Citas literales verificadas por el servidor"
                    : "Selección de pasajes (modo heredado)"}
                </dd>
              </div>
              <div>
                <dt>Contexto y tiempo máximo</dt>
                <dd>
                  {system.runtime.context_tokens} tokens · {system.runtime.timeout_seconds} s por llamada
                </dd>
              </div>
              <div>
                <dt>Memoria y concurrencia</dt>
                <dd>
                  Modelo residente {system.runtime.keep_alive} · {system.runtime.max_concurrent_turns} consulta
                  {system.runtime.max_concurrent_turns === 1 ? "" : "s"} a la vez
                </dd>
              </div>
              <div>
                <dt>Endpoint</dt>
                <dd>{system.runtime.local_endpoint ? "En este equipo" : "Servidor externo configurado"}</dd>
              </div>
            </dl>
          </section>
          <section className="settingSection surface">
                <div>
                  <h3>Prueba local de Ollama</h3>
                  <p>
                    Comprueba una respuesta estructurada y un embedding con texto ficticio. No envía
                    tus documentos ni ejecuta herramientas.
                  </p>
                  <p>
                    El resultado describe esa prueba, no una conexión permanente. Caduca a los 5
                    minutos o al cambiar la configuración.
                  </p>
                </div>
                <div className="localCheckControls">
                  <button
                    className="ghost"
                    onClick={() => void onCheckLocal()}
                    disabled={checkingLocal}
                    aria-busy={checkingLocal}
                  >
                    <RefreshCw size={16} aria-hidden="true" />
                    {checkingLocal ? "Verificando Ollama…" : "Verificar Ollama"}
                  </button>
                  <div role="status" aria-live="polite">
                    {checkingLocal ? (
                      <p>
                        Las dos pruebas pueden tardar varios minutos si los modelos están fríos.
                        Puedes seguir usando el chat; no se reintentará automáticamente.
                      </p>
                    ) : system.local_check ? (
                      <>
                        <p>{system.local_check.message}</p>
                        <p>
                          <time dateTime={system.local_check.checked_at}>
                            {date(system.local_check.checked_at)}
                          </time>
                        </p>
                      </>
                    ) : (
                      <p>No se ha completado una prueba reciente con esta configuración.</p>
                    )}
                  </div>
                  {localCheckError && (
                    <p role="alert" className="errorText">
                      {localCheckError}
                    </p>
                  )}
                </div>
          </section>
          <section className="settingSection surface">
            <div>
              <h3>Indexación y colecciones</h3>
              <p>
                Búsqueda híbrida (vectorial y texto completo en español) filtrada por workspace,
                estado y colección en ambas ramas.
              </p>
            </div>
            <dl>
              <div>
                <dt>Dimensiones</dt>
                <dd>{system.embeddings.dimensions}</dd>
              </div>
              <div>
                <dt>
                  Colección de última prueba
                </dt>
                <dd>
                  <code translate="no">
                    {system.embeddings.collection ?? "Pendiente de verificar el digest Ollama"}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Formatos y tamaño</dt>
                <dd>PDF, DOCX, TXT y MD, hasta {system.indexing.max_file_mb} MB</dd>
              </div>
              <div>
                <dt>Estrategia</dt>
                <dd>Vector y FTS fusionados con RRF, {system.indexing.top_k} fragmentos</dd>
              </div>
            </dl>
          </section>
          <section className="settingSection surface">
            <div>
              <h3>Voz opcional</h3>
              <p>El chat escrito funciona sin micrófono ni modelos de audio.</p>
            </div>
            <dl>
              <div>
                <dt>Dictado ({system.voice.stt})</dt>
                <dd>
                  {system.voice.stt_configured ? "Ruta local configurada; ejecución no verificada" : "No configurado"}
                </dd>
              </div>
              <div>
                <dt>Lectura en voz alta ({system.voice.tts})</dt>
                <dd>{system.voice.tts_configured ? "Configurado; ejecución no verificada" : "No configurado"}</dd>
              </div>
            </dl>
          </section>
        </>
      )}
      <section className="settingSection surface">
        <div>
          <h3>Apariencia</h3>
          <p>Se guarda solo en este navegador.</p>
        </div>
        <div className="segmentedChoice" role="radiogroup" aria-label="Tema de la interfaz">
          {THEMES.map(([value, label]) => (
            <button
              key={value}
              role="radio"
              aria-checked={theme === value}
              className={theme === value ? "active" : ""}
              onClick={() => setTheme(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>
      <section className="settingSection surface">
        <div>
          <h3>Workspace</h3>
          <p>Los datos y las aprobaciones dependen de tu membresía verificada en el servidor.</p>
        </div>
        <div>
          <p>
            Estás en <strong>{workspace}</strong>.
          </p>
          <form
            className="workspaceCreate"
            onSubmit={(e) => {
              e.preventDefault();
              const name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
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
            <button className="primary" disabled={creating}>
              {creating ? "Creando…" : "Crear workspace"}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
