"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Account } from "./account";
import type {
  ChatResult,
  ChunkPage,
  DocumentItem,
  Mode,
  PendingAction,
  Source,
  View,
} from "./product-types";
import { EmptyState, Inspector, Spinner } from "./product-ui";
import { ChatView } from "./chat/chat-view";
import type { ComposerHandle } from "./chat/composer";
import { NAV_ITEMS, Sidebar } from "./layout/sidebar";
import { Topbar } from "./layout/topbar";
import { ActivityView } from "./views/activity-view";
import { ApprovalsView } from "./views/approvals-view";
import { KnowledgeView } from "./views/knowledge-view";
import { ProviderContext, SettingsView } from "./views/settings-view";
import { WorkspaceView } from "./views/workspace-view";
import { useChat } from "@/hooks/use-chat";
import { applyTheme } from "@/hooks/use-theme";
import { useVoice } from "@/hooks/use-voice";
import { useWorkspaceData, type ResourceName } from "@/hooks/use-workspace-data";
import { ApiError, errorMessage, jsonBody, request } from "@/lib/api";

const VIEW_RESOURCES: Record<View, ResourceName[]> = {
  Workspace: ["actions", "activity", "documents", "conversations"],
  Copilot: [],
  Knowledge: ["documents"],
  Approvals: ["actions"],
  Activity: ["activity"],
  Settings: ["system"],
};

/** Workspace shell. Remounted per workspace by AccountGate, so state never crosses workspaces. */
export function Copilot({
  account,
  onSignOut,
  onWorkspace,
}: {
  account: Account;
  onSignOut: () => Promise<void>;
  onWorkspace: (id: string) => Promise<void>;
}) {
  const data = useWorkspaceData();
  const { refresh, setActions, setConversations, setSystem } = data;
  const [view, setView] = useState<View>("Workspace");
  const [viewBusy, setViewBusy] = useState(false);
  const viewRequest = useRef(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("ASK");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deciding, setDeciding] = useState<string | null>(null);
  const decisionRef = useRef(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [checkingLocal, setCheckingLocal] = useState(false);
  const [localCheckError, setLocalCheckError] = useState("");
  const localCheckRequest = useRef(false);
  const [inspected, setInspected] = useState<Source | null>(null);
  const [inspectDoc, setInspectDoc] = useState<DocumentItem | null>(null);
  const [chunkPage, setChunkPage] = useState<ChunkPage | null>(null);
  const [inspectBusy, setInspectBusy] = useState(false);
  const [inspectError, setInspectError] = useState("");
  const composer = useRef<ComposerHandle>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);

  const voice = useVoice(setError);
  const { speak } = voice;
  const onSettled = useCallback(
    (result: ChatResult | null) => {
      refresh("conversations", "actions").catch((err) => setError(errorMessage(err)));
      if (result) void speak(result.answer);
    },
    [refresh, speak],
  );
  const chat = useChat({ onSettled });

  useEffect(() => {
    mounted.current = true;
    applyTheme();
    return () => {
      mounted.current = false;
    };
  }, []);

  // While a synchronous upload runs, reflect server-side status changes in Knowledge.
  useEffect(() => {
    if (!uploading || view !== "Knowledge") return;
    const timer = setInterval(() => refresh("documents").catch(() => {}), 1500);
    return () => clearInterval(timer);
  }, [uploading, view, refresh]);

  const locked = chat.busy !== "idle" || !!deciding || !!deleting || !!reindexing || uploading;
  const workspaceName =
    account.workspaces.find((w) => w.id === account.workspace_id)?.name ?? "Workspace";
  const pendingCount = data.actions.filter((a) => a.status === "PENDING").length;
  const conversationTitle =
    data.conversations.find((c) => c.id === chat.conversationId)?.title ?? null;

  const changeView = useCallback(
    async (next: View) => {
      const version = ++viewRequest.current;
      setView(next);
      setMenuOpen(false);
      setError("");
      setNotice("");
      const resources = VIEW_RESOURCES[next];
      if (!resources.length) {
        setViewBusy(false);
        return;
      }
      setViewBusy(true);
      try {
        await refresh(...resources);
      } catch (err) {
        if (mounted.current) setError(errorMessage(err));
      } finally {
        if (mounted.current && viewRequest.current === version) setViewBusy(false);
      }
    },
    [refresh],
  );

  const openConversation = useCallback(
    async (id: string) => {
      if (deciding) return;
      setMenuOpen(false);
      setView("Copilot");
      await chat.open(id);
    },
    [chat, deciding],
  );

  const newConversation = useCallback(() => {
    chat.reset();
    setMenuOpen(false);
    setView("Copilot");
    setError("");
  }, [chat]);

  const send = useCallback(
    (text: string) => {
      if (deciding || chat.busy !== "idle") return Promise.resolve(false);
      setError("");
      setNotice("");
      voice.stopAudio();
      voice.cancelRecording();
      return chat.send(text, mode);
    },
    [chat, deciding, mode, voice],
  );

  async function decide(action: PendingAction, approved: boolean) {
    if (decisionRef.current) return;
    decisionRef.current = true;
    setDeciding(action.id);
    setError("");
    try {
      const d = await request<{ status: string; ticket?: { id: number; title: string } }>(
        `/api/actions/${action.id}/decision`,
        jsonBody({ approved }),
      );
      setActions((current) =>
        current.map((a) =>
          a.id === action.id
            ? { ...a, status: d.status === "executed" ? "EXECUTED" : "REJECTED" }
            : a,
        ),
      );
      chat.resolveAction(
        action.id,
        d.status === "executed" && d.ticket
          ? `Acción ejecutada. Ticket #${d.ticket.id}: ${d.ticket.title}.`
          : "Acción rechazada. No se ejecutó.",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already decided elsewhere (double click, retry, another tab): show the truth.
        setNotice(`${err.message} Se ha actualizado la lista con el estado real.`);
        refresh("actions").catch(() => {});
      } else setError(errorMessage(err));
    } finally {
      decisionRef.current = false;
      setDeciding(null);
    }
  }

  async function removeDocument(id: string) {
    if (deleting || !window.confirm("¿Eliminar este documento y todos sus fragmentos indexados?"))
      return;
    setDeleting(id);
    try {
      await request(`/api/documents/${id}`, { method: "DELETE" });
      await refresh("documents");
      setNotice("Documento eliminado del conocimiento del workspace.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(null);
    }
  }

  async function upload(file: File) {
    if (uploading) return;
    if (!/\.(pdf|docx|txt|md)$/i.test(file.name)) {
      setError("Formato no admitido. Usa PDF, DOCX, TXT o MD.");
      return;
    }
    if (!file.size) {
      setError("El archivo está vacío.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("El archivo supera 20 MB");
      return;
    }
    setError("");
    setNotice("");
    setView("Knowledge");
    const form = new FormData();
    form.append("file", file);
    setUploading(true);
    try {
      const d = await request<{ filename: string; chunks: number }>("/api/documents", {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(300_000),
      });
      setNotice(
        `${d.filename} indexado: ${d.chunks} ${d.chunks === 1 ? "fragmento disponible" : "fragmentos disponibles"}.`,
      );
    } catch (err) {
      setError(`No pude indexar el documento: ${errorMessage(err)}`);
    } finally {
      setUploading(false);
      refresh("documents").catch((err) => setError(errorMessage(err)));
    }
  }

  async function reindex(id: string) {
    if (
      reindexing ||
      !window.confirm("¿Reindexar este documento con el proveedor y modelo de embeddings configurados?")
    )
      return;
    setReindexing(id);
    setError("");
    try {
      await request(`/api/documents/${id}/reindex`, {
        method: "POST",
        signal: AbortSignal.timeout(300_000),
      });
      await refresh("documents");
      setNotice("Documento reindexado con el modelo configurado.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setReindexing(null);
    }
  }

  async function createWorkspace(name: string) {
    if (creatingWorkspace) return;
    setCreatingWorkspace(true);
    setError("");
    try {
      const created = await request<{ id: string }>("/api/auth/workspaces", jsonBody({ name }));
      await onWorkspace(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      if (mounted.current) setCreatingWorkspace(false);
    }
  }

  async function checkLocalProvider() {
    const system = data.system;
    if (
      localCheckRequest.current ||
      !system ||
      system.demo ||
      system.generation.provider !== "ollama" ||
      system.embeddings.provider !== "ollama"
    )
      return;
    const signature = (s: typeof system) =>
      JSON.stringify([s.demo, s.generation.provider, s.generation.model, s.embeddings.provider, s.embeddings.model, s.embeddings.dimensions]);
    const started = signature(system);
    localCheckRequest.current = true;
    setCheckingLocal(true);
    setLocalCheckError("");
    try {
      const checked = await request<typeof system>("/api/system/check-local", {
        method: "POST",
        signal: AbortSignal.timeout(300_000),
      });
      if (mounted.current && checked.generation)
        setSystem((current) => (current && signature(current) === started ? checked : current));
    } catch (err) {
      if (mounted.current) {
        const timedOut = err instanceof Error && err.name === "TimeoutError";
        setLocalCheckError(
          timedOut
            ? "La espera de la prueba ha terminado; el backend puede seguir procesándola. Actualiza el estado antes de volver a verificar."
            : `${errorMessage(err)} Comprueba el servicio Ollama y los modelos; actualiza el estado antes de repetir la prueba.`,
        );
      }
    } finally {
      localCheckRequest.current = false;
      if (mounted.current) setCheckingLocal(false);
    }
  }

  async function inspectDocument(doc: DocumentItem, offset = 0) {
    setInspectDoc(doc);
    setInspected(null);
    setInspectBusy(true);
    setInspectError("");
    try {
      setChunkPage(await request<ChunkPage>(`/api/documents/${doc.id}/chunks?offset=${offset}`));
    } catch (err) {
      setInspectError(errorMessage(err));
    } finally {
      setInspectBusy(false);
    }
  }

  async function renameConversation(title: string) {
    const id = chat.conversationId;
    if (!id) return;
    try {
      await request(`/api/conversations/${id}`, jsonBody({ title }, "PATCH"));
      setConversations((current) => current.map((c) => (c.id === id ? { ...c, title } : c)));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function archiveConversation() {
    const id = chat.conversationId;
    if (!id) return;
    try {
      await request(`/api/conversations/${id}`, jsonBody({ archived: true }, "PATCH"));
      setConversations((current) => current.filter((c) => c.id !== id));
      chat.reset();
      setNotice("Conversación archivada. Su historial y sus decisiones se conservan en Actividad.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const onSource = useCallback((source: Source) => {
    setInspected(source);
    setInspectDoc(null);
  }, []);
  // Stable callback for memoized messages; always calls the latest `decide`.
  const decideRef = useRef(decide);
  useEffect(() => {
    decideRef.current = decide;
  });
  const onDecide = useCallback(
    (action: PendingAction, approved: boolean) => void decideRef.current(action, approved),
    [],
  );

  const shownError = error || chat.error || data.loadError;
  const feedback = (
    <div className="feedbackArea">
      {voice.audioStatus && (
        <div className="noticeBanner" role="status">
          {voice.audioStatus}
          <button className="textButton" onClick={voice.stopAudio}>
            Detener audio
          </button>
        </div>
      )}
      {notice && (
        <div className="noticeBanner" role="status">
          {notice}
        </div>
      )}
      {shownError && (
        <div role="alert" className="errorBanner">
          <span>{shownError}</span>
          {chat.retry && (
            <button
              className="textButton"
              onClick={() => {
                composer.current?.setText(chat.recover());
                setError("");
                chat.setError("");
              }}
            >
              Recuperar mensaje para reintentar
            </button>
          )}
        </div>
      )}
      {(data.initialLoading || viewBusy) && view !== "Copilot" && (
        <p className="streamStatus" role="status">
          <Spinner /> Cargando el workspace…
        </p>
      )}
    </div>
  );

  return (
    <main className={`shell view-${view.toLowerCase()} ${menuOpen ? "menuOpen" : ""}`}>
      <a className="skipLink" href="#main-content">
        Saltar al contenido
      </a>
      <div className="backdropScene" aria-hidden="true" />
      <Sidebar
        account={account}
        workspaceName={workspaceName}
        view={view}
        open={menuOpen}
        pendingCount={pendingCount}
        conversations={data.conversations}
        conversationId={chat.conversationId}
        locked={locked}
        onView={changeView}
        onWorkspace={(id) => onWorkspace(id).catch((err) => setError(errorMessage(err)))}
        onConversation={openConversation}
        onNewConversation={newConversation}
        onSignOut={() => onSignOut().catch((err) => setError(errorMessage(err)))}
      />
      <section className="content">
        {data.system?.demo && (
          <div className="demoRibbon">
            <strong>Demo de desarrollo</strong>
            <span>Datos ficticios · IA simulada · Sin conexión con Gemini</span>
          </div>
        )}
        <Topbar
          workspaceName={workspaceName}
          title={NAV_ITEMS.find((n) => n.view === view)?.label ?? view}
          menuOpen={menuOpen}
          onMenu={() => setMenuOpen((open) => !open)}
          isCopilot={view === "Copilot"}
          conversationTitle={conversationTitle}
          locked={locked}
          speechEnabled={voice.speechEnabled}
          onSpeech={voice.toggleSpeech}
          onNewConversation={newConversation}
          onRename={renameConversation}
          onArchive={archiveConversation}
        />
        {view === "Copilot" ? (
          <ChatView
            ref={composer}
            system={data.system}
            messages={chat.messages}
            draft={chat.draft}
            loadingHistory={chat.busy === "loading"}
            deciding={!!deciding || chat.busy !== "idle"}
            mode={mode}
            onMode={setMode}
            listening={voice.listening}
            onSend={send}
            onStop={chat.stop}
            onListen={() => void voice.listen((text) => composer.current?.setText(text))}
            onSource={onSource}
            onDecide={onDecide}
            feedback={feedback}
            context={<ProviderContext system={data.system} />}
          />
        ) : (
          <div
            id="main-content"
            tabIndex={-1}
            className="mainScroll"
            aria-busy={data.initialLoading || viewBusy}
          >
            {feedback}
            {view === "Workspace" && (
              <WorkspaceView
                name={workspaceName}
                docs={data.documents}
                actions={data.actions}
                activity={data.activity}
                conversations={data.conversations}
                system={data.system}
                onView={changeView}
                onPrompt={(text) => {
                  newConversation();
                  requestAnimationFrame(() => composer.current?.setText(text));
                }}
                onUpload={() => fileRef.current?.click()}
                onConversation={openConversation}
              />
            )}
            {view === "Knowledge" && (
              <KnowledgeView
                docs={data.documents}
                system={data.system}
                busy={uploading || !!deleting || !!reindexing || chat.busy !== "idle"}
                operation={
                  uploading
                    ? "Subiendo e indexando el documento…"
                    : reindexing
                      ? "Reindexando con la colección activa…"
                      : ""
                }
                processing={uploading || !!reindexing}
                onUpload={() => fileRef.current?.click()}
                onRemove={removeDocument}
                onReindex={reindex}
                onInspect={inspectDocument}
              />
            )}
            {view === "Approvals" && (
              <ApprovalsView
                actions={data.actions}
                busy={!!deciding || chat.busy !== "idle"}
                onDecide={decide}
                onConversation={openConversation}
              />
            )}
            {view === "Activity" && (
              <ActivityView events={data.activity} onRefresh={() => changeView("Activity")} />
            )}
            {view === "Settings" && (
              <SettingsView
                system={data.system}
                workspace={workspaceName}
                onCreate={createWorkspace}
                creating={creatingWorkspace}
                onReload={() => changeView("Settings")}
                checkingLocal={checkingLocal}
                localCheckError={localCheckError}
                onCheckLocal={checkLocalProvider}
              />
            )}
          </div>
        )}
      </section>
      <input
        ref={fileRef}
        hidden
        type="file"
        accept=".pdf,.docx,.txt,.md"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void upload(file);
        }}
      />
      {inspected && (
        <Inspector
          title={inspected.filename}
          subtitle={[
            inspected.section,
            inspected.page ? `Página ${inspected.page}` : "Sin páginas fiables",
            `Fragmento #${inspected.chunk_id}`,
          ]
            .filter(Boolean)
            .join(", ")}
          onClose={() => setInspected(null)}
        >
          <h3 className="inspectorLabel">Pasaje almacenado completo</h3>
          <blockquote>{inspected.excerpt}</blockquote>
          <p className="footnote">
            Similitud {inspected.score.toFixed(3)}: mide cercanía, no certeza ni aplicabilidad. La
            respuesta cita frases literales de este pasaje.
          </p>
          {inspected.document_id && (
            <button
              className="ghost"
              onClick={() =>
                inspectDocument({ id: inspected.document_id!, filename: inspected.filename } as DocumentItem)
              }
            >
              Ver todos los fragmentos del documento
            </button>
          )}
        </Inspector>
      )}
      {inspectDoc && (
        <Inspector
          title={inspectDoc.filename}
          subtitle="Texto conservado, solo del workspace actual"
          onClose={() => {
            setInspectDoc(null);
            setChunkPage(null);
          }}
        >
          {inspectBusy ? (
            <p role="status">
              <Spinner /> Cargando fragmentos…
            </p>
          ) : inspectError ? (
            <p role="alert">{inspectError}</p>
          ) : (
            <>
              {chunkPage?.chunks.map((c) => (
                <section className="chunkBlock" key={c.id}>
                  <h3 className="inspectorLabel">
                    Fragmento {c.index + 1}
                    {c.section ? `, ${c.section}` : ""}
                    {c.page ? `, página ${c.page}` : ""}
                  </h3>
                  <blockquote>{c.content}</blockquote>
                </section>
              ))}
              {chunkPage?.total === 0 && (
                <EmptyState title="Sin fragmentos conservados">
                  Este documento no contiene texto indexado. Revisa el error de indexación y vuelve
                  a subir un archivo válido.
                </EmptyState>
              )}
              {chunkPage && chunkPage.total > 0 && (
                <div className="pagination">
                  <button
                    className="ghost small"
                    disabled={chunkPage.offset === 0}
                    onClick={() => inspectDocument(inspectDoc, Math.max(0, chunkPage.offset - 25))}
                  >
                    Anterior
                  </button>
                  <span>
                    {chunkPage.offset + 1}–{Math.min(chunkPage.offset + 25, chunkPage.total)} de{" "}
                    {chunkPage.total}
                  </span>
                  <button
                    className="ghost small"
                    disabled={chunkPage.offset + 25 >= chunkPage.total}
                    onClick={() => inspectDocument(inspectDoc, chunkPage.offset + 25)}
                  >
                    Siguiente
                  </button>
                </div>
              )}
            </>
          )}
        </Inspector>
      )}
    </main>
  );
}
