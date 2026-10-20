"use client";

import type { Account } from "./account";
import { readChatStream } from "./stream";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Bot,
  FileText,
  Mic,
  Send,
  ShieldCheck,
  Square,
  Volume2,
  VolumeX,
  LayoutGrid,
  Settings2,
  History,
  Plus,
  ArrowUpRight,
  LogOut,
  PanelLeftClose,
  Menu,
  LoaderCircle,
} from "lucide-react";
import type {
  DocumentItem,
  Activity,
  Conversation,
  Source,
  PendingAction,
  Message,
  SystemInfo,
  View,
  ChunkPage,
} from "./product-types";
import {
  ActionCard,
  EmptyState,
  AnswerText,
  Inspector,
  Insufficient,
  SourceChip,
} from "./product-ui";
import {
  WorkspaceView,
  KnowledgeView,
  ApprovalsView,
  ActivityView,
  SettingsView,
} from "./product-views";

const API = "";
const errorMessage = (error: unknown) => {
  const value =
    typeof error === "object" && error !== null
      ? (error as { name?: unknown; message?: unknown })
      : null;
  if (value?.name === "AbortError")
    return "Consulta detenida. Revisa el historial antes de repetir una acción.";
  if (value?.name === "TimeoutError")
    return "El servidor tardó demasiado. Revisa el historial antes de repetir una acción; podría haberse completado.";
  return typeof value?.message === "string"
    ? value.message
    : "Error inesperado";
};
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(90000),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `Solicitud fallida (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export function Copilot({
  account,
  onSignOut,
  onWorkspace,
}: {
  account: Account;
  onSignOut: () => Promise<void>;
  onWorkspace: (id: string) => Promise<void>;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [viewBusy, setViewBusy] = useState(false);
  const viewRequest = useRef(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [inspected, setInspected] = useState<Source | null>(null);
  const [chunkPage, setChunkPage] = useState<ChunkPage | null>(null);
  const [inspectDoc, setInspectDoc] = useState<DocumentItem | null>(null);
  const [inspectBusy, setInspectBusy] = useState(false);
  const [inspectError, setInspectError] = useState("");
  const chatRequest = useRef<AbortController | null>(null);
  const recordingCancelled = useRef(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const audioRequest = useRef<AbortController | null>(null);
  const followScroll = useRef(true);
  const [retry, setRetry] = useState("");
  const [streamStatus, setStreamStatus] = useState("");
  const submitting = useRef(false);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"ASK" | "DO">("ASK");
  const [voice, setVoice] = useState(false);
  const [audioStatus, setAudioStatus] = useState("");
  const [listening, setListening] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [view, setView] = useState<View>("Workspace");
  const [activity, setActivity] = useState<Activity[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState("");
  const [deciding, setDeciding] = useState<string | null>(null);
  const decisionRef = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const mountedRef = useRef(true);
  const [reindexing, setReindexing] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const voiceRef = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const refreshDocs = async () => {
    setDocuments(await request<DocumentItem[]>("/api/documents"));
  };
  useEffect(() => {
    let active = true;
    mountedRef.current = true;
    const requests = [
      request<DocumentItem[]>("/api/documents"),
      request<Conversation[]>("/api/conversations"),
      request<SystemInfo>("/api/system"),
      request<PendingAction[]>("/api/actions"),
      request<Activity[]>("/api/activity"),
    ] as const;
    Promise.allSettled(requests).then((results) => {
      if (!active) return;
      const [docs, chats, config, pending, events] = results;
      if (docs.status === "fulfilled") setDocuments(docs.value);
      if (chats.status === "fulfilled") setConversations(chats.value);
      if (config.status === "fulfilled" && config.value.generation)
        setSystem(config.value);
      if (pending.status === "fulfilled") setActions(pending.value);
      if (events.status === "fulfilled") setActivity(events.value);
      const failure = results.find((r) => r.status === "rejected");
      if (failure?.status === "rejected")
        setError(errorMessage(failure.reason));
      setInitialLoading(false);
    });
    return () => {
      active = false;
      mountedRef.current = false;
      recordingCancelled.current = true;
      chatRequest.current?.abort();
      mediaRef.current?.getTracks().forEach((t) => t.stop());
      recorderRef.current?.state === "recording" && recorderRef.current.stop();
      audioRequest.current?.abort();
      audioRef.current?.pause();
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    };
  }, []);
  useEffect(() => {
    if (!loading || view !== "Knowledge") return;
    const timer = setInterval(() => {
      request<DocumentItem[]>("/api/documents")
        .then(setDocuments)
        .catch(() => {});
    }, 1500);
    return () => clearInterval(timer);
  }, [loading, view]);
  async function changeView(next: View) {
    const version = ++viewRequest.current;
    setView(next);
    setMenuOpen(false);
    setError("");
    setNotice("");
    if (next === "Copilot") {
      setViewBusy(false);
      return;
    }
    setViewBusy(true);
    try {
      const updates: Promise<void>[] = [];
      if (next === "Approvals" || next === "Workspace")
        updates.push(request<PendingAction[]>("/api/actions").then(setActions));
      if (next === "Activity" || next === "Workspace")
        updates.push(request<Activity[]>("/api/activity").then(setActivity));
      if (next === "Knowledge")
        updates.push(
          request<DocumentItem[]>("/api/documents").then(setDocuments),
        );
      if (next === "Settings")
        updates.push(
          request<SystemInfo>("/api/system").then((config) => {
            if (config.generation) setSystem(config);
          }),
        );
      await Promise.all(updates);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      if (viewRequest.current === version) setViewBusy(false);
    }
  }
  async function openConversation(id: string) {
    if (loading || deciding) return;
    setLoading(true);
    setError("");
    try {
      const data = await request<{
        messages: Message[];
        pending_actions: PendingAction[];
      }>(`/api/conversations/${id}`);
      setMessages([
        ...data.messages,
        ...data.pending_actions.map((pending) => ({
          role: "assistant" as const,
          content: "Acción pendiente de confirmación.",
          pending,
        })),
      ]);
      setConversationId(id);
      setView("Copilot");
      setMenuOpen(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }
  function stopAudio() {
    setAudioStatus("");
    audioRequest.current?.abort();
    audioRequest.current = null;
    audioRef.current?.pause();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
    audioRef.current = null;
  }

  useEffect(() => {
    if (followScroll.current)
      endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function speak(text: string) {
    if (!voiceRef.current) return;
    try {
      stopAudio();
      const controller = new AbortController();
      audioRequest.current = controller;
      setAudioStatus("Generando audio…");
      const r = await fetch(`${API}/api/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ text: text.slice(0, 3800) }),
      });
      if (!r.ok)
        throw new Error(
          "No se pudo generar el audio. La respuesta escrita sigue disponible.",
        );
      const blob = await r.blob();
      if (!voiceRef.current || controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      audioUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = stopAudio;
      audio.onerror = () => {
        stopAudio();
        setError("No se pudo reproducir el audio");
      };
      await audio.play();
      setAudioStatus("Reproduciendo voz de IA…");
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      stopAudio();
      setError(errorMessage(err));
    }
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading || submitting.current || deciding) return;
    followScroll.current = true;
    stopAudio();
    recordingCancelled.current = true;
    recorderRef.current?.state === "recording" && recorderRef.current.stop();
    submitting.current = true;
    setError("");
    setRetry("");
    setInput("");
    setLoading(true);
    setStreamStatus("Buscando fuentes…");
    setStreaming(true);
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ]);
    const controller = new AbortController();
    chatRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 300000);
    let answer = "";
    try {
      const response = await fetch("/api/chat/stream", {
        signal: controller.signal,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          mode,
        }),
      });
      await readChatStream<{
        conversation_id: string;
        answer: string;
        sources: Source[];
        pending_action: PendingAction | null;
      }>(response, (event) => {
        if (event.type === "delta") {
          setStreamStatus("Generando respuesta…");
          setMessages((m) =>
            m.map((item, i) =>
              i === m.length - 1
                ? { ...item, content: item.content + event.text }
                : item,
            ),
          );
        }
        if (event.type === "status") setStreamStatus(event.text);
        if (event.type === "done") {
          const data = event.data;
          answer = data.answer;
          setConversationId(data.conversation_id);
          setMessages((m) =>
            m.map((item, i) =>
              i === m.length - 1
                ? {
                    role: "assistant",
                    content: data.answer,
                    sources: data.sources,
                    pending: data.pending_action ?? undefined,
                  }
                : item,
            ),
          );
        }
      });
      request<Conversation[]>("/api/conversations")
        .then(setConversations)
        .catch((err) => setError(errorMessage(err)));
      request<PendingAction[]>("/api/actions")
        .then(setActions)
        .catch((err) => setError(errorMessage(err)));
      void speak(answer);
    } catch (err) {
      setError(errorMessage(err));
      setRetry(text);
      setMessages((m) =>
        m.map((item, i) =>
          i === m.length - 1
            ? {
                role: "assistant",
                failed: true,
                content:
                  "La respuesta no se completó. Revisa el historial antes de repetir una acción.",
              }
            : item,
        ),
      );
    } finally {
      clearTimeout(timeout);
      chatRequest.current = null;
      submitting.current = false;
      setStreaming(false);
      setLoading(false);
      setStreamStatus("");
    }
  }

  async function removeDocument(id: string) {
    if (deleting) return;
    if (
      !window.confirm(
        "¿Eliminar este documento y todos sus fragmentos indexados?",
      )
    )
      return;
    setDeleting(id);
    try {
      await request(`/api/documents/${id}`, { method: "DELETE" });
      await refreshDocs();
      setNotice("Documento eliminado del conocimiento del workspace.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(null);
    }
  }

  async function upload(file: File) {
    if (loading) return;
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
    setStreamStatus("Subiendo e indexando el documento…");
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/documents`, {
        signal: AbortSignal.timeout(300000),
        method: "POST",
        body: fd,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Error al indexar");
      setNotice(
        `${d.filename} indexado: ${d.chunks} ${d.chunks === 1 ? "fragmento disponible" : "fragmentos disponibles"}.`,
      );
      await refreshDocs();
    } catch (err) {
      setError(`No pude indexar el documento: ${errorMessage(err)}`);
    } finally {
      setLoading(false);
      setStreamStatus("");
      setUploading(false);
      refreshDocs().catch((err) => setError(errorMessage(err)));
    }
  }

  async function listen() {
    if (listening) {
      if (recorderRef.current?.state === "recording")
        recorderRef.current.stop();
      else {
        recordingCancelled.current = true;
        setListening(false);
      }
      return;
    }
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setError(
        "Grabación no disponible. Usa un navegador compatible en localhost o HTTPS; puedes seguir escribiendo.",
      );
      return;
    }
    recordingCancelled.current = false;
    setListening(true);
    setError("");
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current || recordingCancelled.current) {
        media.getTracks().forEach((t) => t.stop());
        return;
      }
      mediaRef.current = media;
      const recorder = new MediaRecorder(media);
      recorderRef.current = recorder;
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      const timer = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 60000);
      recorder.onerror = () => {
        clearTimeout(timer);
        media.getTracks().forEach((t) => t.stop());
        setListening(false);
        setError("No se pudo grabar el audio. Puedes seguir escribiendo.");
      };
      recorder.onstop = async () => {
        clearTimeout(timer);
        media.getTracks().forEach((t) => t.stop());
        if (!mountedRef.current || recordingCancelled.current) return;
        setListening(false);
        try {
          const form = new FormData();
          form.append(
            "file",
            new Blob(chunks, { type: recorder.mimeType }),
            "recording.webm",
          );
          const result = await request<{ text: string }>(
            "/api/voice/transcribe",
            { method: "POST", body: form },
          );
          if (mountedRef.current) setInput(result.text);
        } catch (err) {
          if (mountedRef.current) setError(errorMessage(err));
        }
      };
      recorder.start();
    } catch (err) {
      setListening(false);
      mediaRef.current?.getTracks().forEach((t) => t.stop());
      setError(
        err instanceof Error && err.name === "NotAllowedError"
          ? "Permiso de micrófono denegado. Puedes seguir escribiendo."
          : errorMessage(err),
      );
    }
  }

  async function reindex(id: string) {
    if (
      reindexing ||
      !window.confirm(
        "¿Reindexar este documento con el proveedor y modelo de embeddings configurados?",
      )
    )
      return;
    setReindexing(id);
    setError("");
    try {
      await request(`/api/documents/${id}/reindex`, {
        method: "POST",
        signal: AbortSignal.timeout(300000),
      });
      await refreshDocs();
      setNotice("Documento reindexado con el modelo configurado.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setReindexing(null);
    }
  }

  async function decide(action: PendingAction, approved: boolean) {
    if (decisionRef.current) return;
    decisionRef.current = true;
    setDeciding(action.id);
    setError("");
    try {
      const d = await request<{
        status: string;
        ticket?: { id: number; title: string };
      }>(`/api/actions/${action.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });
      setActions((current) =>
        current.map((a) =>
          a.id === action.id
            ? {
                ...a,
                status: d.status === "executed" ? "EXECUTED" : "REJECTED",
              }
            : a,
        ),
      );
      setMessages((m) => [
        ...m.map((item) =>
          item.pending?.id === action.id
            ? { ...item, pending: undefined }
            : item,
        ),
        {
          role: "assistant",
          content:
            d.status === "executed" && d.ticket
              ? `Acción ejecutada. Ticket #${d.ticket.id}: ${d.ticket.title}.`
              : "Acción rechazada. No se ejecutó.",
        },
      ]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      decisionRef.current = false;
      setDeciding(null);
    }
  }

  async function createWorkspace(name: string) {
    if (creatingWorkspace) return;
    setCreatingWorkspace(true);
    setError("");
    try {
      const created = await request<{ id: string }>("/api/auth/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await onWorkspace(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreatingWorkspace(false);
    }
  }
  async function inspectDocument(doc: DocumentItem, offset = 0) {
    setInspectDoc(doc);
    setInspected(null);
    setInspectBusy(true);
    setInspectError("");
    try {
      setChunkPage(
        await request<ChunkPage>(
          `/api/documents/${doc.id}/chunks?offset=${offset}`,
        ),
      );
    } catch (err) {
      setInspectError(errorMessage(err));
    } finally {
      setInspectBusy(false);
    }
  }
  const workspaceName =
    account.workspaces.find((w) => w.id === account.workspace_id)?.name ??
    "Workspace";
  const navItems = [
    { view: "Workspace", label: "Workspace", icon: LayoutGrid },
    { view: "Copilot", label: "Copilot", icon: Bot },
    { view: "Knowledge", label: "Knowledge", icon: FileText },
    { view: "Approvals", label: "Aprobaciones", icon: ShieldCheck },
    { view: "Activity", label: "Actividad", icon: History },
    { view: "Settings", label: "Configuración", icon: Settings2 },
  ] as const;
  const pendingCount = actions.filter((a) => a.status === "PENDING").length;
  const newConversation = () => {
    setMessages([]);
    setMenuOpen(false);
    setConversationId(null);
    setView("Copilot");
    setError("");
  };
  const prompt = (text: string) => {
    newConversation();
    setInput(text);
  };
  const sourceOpen = (source: Source) => {
    setInspected(source);
    setInspectDoc(null);
  };
  return (
    <main className="shell">
      <a className="skipLink" href="#main-content">
        Saltar al contenido
      </a>
      <aside
        className={`sidebar ${menuOpen ? "expanded" : ""}`}
        aria-label="Navegación del workspace"
      >
        <button
          className="mobileToggle"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <span className="wordmark">
            MAZMI<span> / OPS</span>
          </span>
          {menuOpen ? <PanelLeftClose size={20} /> : <Menu size={20} />}
        </button>
        <div className="brand">
          <div className="brandmark">
            M<span>·</span>
          </div>
          <div>
            <b>
              MAZMI<span> SYSTEMS</span>
            </b>
            <small>Operations intelligence</small>
          </div>
        </div>
        <div className="workspacePicker">
          <span className="workspaceMonogram">{workspaceName[0]}</span>
          <label>
            <span>ESPACIO DE TRABAJO</span>
            <select
              aria-label="Workspace"
              disabled={loading || !!deciding || !!deleting || !!reindexing}
              value={account.workspace_id}
              onChange={(e) =>
                onWorkspace(e.target.value).catch((err) =>
                  setError(errorMessage(err)),
                )
              }
            >
              {account.workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <nav>
          {navItems.map(({ view: next, label, icon: Icon }) => (
            <button
              key={next}
              className={`nav ${view === next ? "active" : ""}`}
              aria-current={view === next ? "page" : undefined}
              onClick={() => changeView(next)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {next === "Approvals" && pendingCount > 0 && (
                <b className="navCount">{pendingCount}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="conversationList">
          <div className="sectionTitle">
            <span>CONVERSACIONES</span>
            <button
              className="iconButton"
              aria-label="Nueva conversación"
              disabled={loading || !!deciding}
              onClick={newConversation}
            >
              <Plus size={17} />
            </button>
          </div>
          {conversations.map((c) => (
            <button
              className={`conversationLink ${conversationId === c.id ? "active" : ""}`}
              disabled={loading || !!deciding}
              key={c.id}
              onClick={() => openConversation(c.id)}
            >
              {c.title}
            </button>
          ))}
          {!conversations.length && (
            <p className="muted small">
              Tus consultas quedarán guardadas aquí.
            </p>
          )}
        </div>
        <div className="sidebarFooter">
          <p>
            <ShieldCheck size={15} /> Datos del workspace actual
          </p>
          <div>
            <span className="accountAvatar">
              {account.email[0].toUpperCase()}
            </span>
            <span className="accountEmail">{account.email}</span>
            <button
              className="iconButton"
              aria-label="Cerrar sesión"
              disabled={loading || !!deciding}
              onClick={() =>
                onSignOut().catch((err) => setError(errorMessage(err)))
              }
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <section className={`content view-${view.toLowerCase()}`}>
        {system?.demo && (
          <div className="demoRibbon">
            <strong>DEMO DE DESARROLLO</strong>
            <span>Datos ficticios · IA simulada · Sin conexión con Gemini</span>
          </div>
        )}
        <header className="topbar">
          <div className="breadcrumb">
            {workspaceName}
            <span>/</span>
            <h1>{navItems.find((n) => n.view === view)?.label}</h1>
          </div>
          <div className="headerActions">
            {view === "Copilot" ? (
              <>
                <div className="segmented" aria-label="Modo de trabajo">
                  <button
                    aria-pressed={mode === "ASK"}
                    disabled={loading}
                    className={mode === "ASK" ? "selected" : ""}
                    onClick={() => setMode("ASK")}
                  >
                    ASK
                  </button>
                  <button
                    aria-pressed={mode === "DO"}
                    disabled={loading}
                    className={mode === "DO" ? "selected do" : ""}
                    onClick={() => setMode("DO")}
                  >
                    DO
                  </button>
                </div>
                <button
                  className={`voice ${voice ? "on" : ""}`}
                  aria-pressed={voice}
                  aria-label="Leer respuestas en voz alta"
                  onClick={() => {
                    voiceRef.current = !voice;
                    setVoice(!voice);
                    if (voice) stopAudio();
                  }}
                >
                  {voice ? <Volume2 size={17} /> : <VolumeX size={17} />}
                </button>
              </>
            ) : (
              <button
                className="quietButton"
                disabled={loading}
                onClick={newConversation}
              >
                Nueva consulta <ArrowUpRight size={16} />
              </button>
            )}
          </div>
        </header>
        <div
          id="main-content"
          aria-busy={initialLoading || viewBusy}
          tabIndex={-1}
          className="mainScroll"
          onScroll={(e) => {
            const el = e.currentTarget;
            followScroll.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
        >
          <div className="feedbackArea">
            {audioStatus && (
              <div className="noticeBanner" role="status">
                {audioStatus}
                <button onClick={stopAudio}>Detener audio</button>
              </div>
            )}
            {notice && (
              <div className="noticeBanner" role="status">
                {notice}
              </div>
            )}
            {error && (
              <div role="alert" className="errorBanner">
                {error}
                {retry && (
                  <button
                    onClick={() => {
                      setInput(retry);
                      setRetry("");
                    }}
                  >
                    Recuperar mensaje para reintentar
                  </button>
                )}
              </div>
            )}
            {(initialLoading || viewBusy) && (
              <p className="streamStatus" role="status">
                <LoaderCircle size={16} /> Cargando el workspace…
              </p>
            )}
          </div>
          {view === "Workspace" && (
            <WorkspaceView
              name={workspaceName}
              docs={documents}
              actions={actions}
              activity={activity}
              system={system}
              onView={changeView}
              onPrompt={prompt}
            />
          )}
          {view === "Knowledge" && (
            <KnowledgeView
              docs={documents}
              system={system}
              busy={loading || !!deleting || !!reindexing}
              operation={
                uploading
                  ? streamStatus
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
              actions={actions}
              busy={!!deciding || loading}
              onDecide={decide}
              onConversation={openConversation}
            />
          )}
          {view === "Activity" && (
            <ActivityView
              events={activity}
              onRefresh={() => changeView("Activity")}
            />
          )}
          {view === "Settings" && (
            <SettingsView
              system={system}
              workspace={workspaceName}
              onCreate={createWorkspace}
              creating={creatingWorkspace}
              onReload={() => changeView("Settings")}
            />
          )}
          {view === "Copilot" && (
            <div className="chatCanvas">
              {!messages.length && (
                <div className="chatWelcome">
                  <span className="eyebrow">MAZMI / COPILOT</span>
                  <h2>
                    Una pregunta.
                    <br />
                    Todo el contexto.
                  </h2>
                  <p>
                    Consulta el conocimiento del workspace o prepara una acción
                    que tú autorizas.
                  </p>
                  <div className="promptList">
                    {[
                      "¿Cuántos días de vacaciones hay?",
                      "¿Qué información hay sobre el acceso?",
                      "Consulta mis tickets",
                    ].map((t) => (
                      <button key={t} onClick={() => setInput(t)}>
                        {t}
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                  </div>
                  {system?.generation.state === "not_configured" && (
                    <p className="setupHint">
                      Gemini todavía no está configurado. Consulta Configuración
                      o utiliza el modo demo de desarrollo.
                    </p>
                  )}
                </div>
              )}
              {messages.map((m, i) => (
                <article key={i} className={`messageRow ${m.role}`}>
                  <div className="messageIdentity">
                    {m.role === "user"
                      ? "TÚ"
                      : system?.demo
                        ? "MAZMI · DEMO"
                        : "MAZMI"}
                    {m.role === "assistant" && m.sources?.length ? (
                      <span>Consulta documental</span>
                    ) : null}
                  </div>
                  <div className="messageBody">
                    {(m.role === "assistant" &&
                      m.content.startsWith(
                        "No encuentro información suficiente",
                      )) ||
                    m.content.startsWith(
                      "Los documentos recuperados contienen información contradictoria",
                    ) ? (
                      <Insufficient text={m.content} />
                    ) : (
                      <AnswerText
                        text={m.content}
                        sources={m.sources ?? []}
                        onSource={sourceOpen}
                      />
                    )}{" "}
                    {m.failed && (
                      <small className="errorText">
                        Respuesta incompleta · no se ha confirmado ninguna
                        ejecución desde este mensaje.
                      </small>
                    )}
                    {m.sources && m.sources.length > 0 && (
                      <div className="sources">
                        <span className="eyebrow">
                          EVIDENCIA RECUPERADA · {m.sources.length}{" "}
                          {m.sources.length === 1 ? "FRAGMENTO" : "FRAGMENTOS"}
                        </span>
                        <div className="sourceGrid">
                          {m.sources.map((source, j) => (
                            <SourceChip
                              key={source.chunk_id}
                              source={source}
                              index={j + 1}
                              selected={m.content.includes(`[${j + 1}]`)}
                              onOpen={() => sourceOpen(source)}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {m.pending && (
                      <ActionCard
                        action={m.pending}
                        busy={!!deciding || loading}
                        onDecide={decide}
                      />
                    )}
                  </div>
                </article>
              ))}
              {loading && (
                <div className="streamStatus" role="status">
                  <LoaderCircle size={16} /> {streamStatus || "Procesando…"}
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>
        {view === "Copilot" && (
          <div className="composerArea">
            <div className={`modeHint ${mode.toLowerCase()}`}>
              <b>{mode}</b>
              {mode === "ASK"
                ? "Consulta conocimiento y herramientas de lectura."
                : "Prepara acciones. Ninguna se ejecuta sin tu aprobación."}
            </div>
            <form className="composer" onSubmit={submit}>
              <textarea
                aria-label="Mensaje al copiloto"
                maxLength={8000}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  mode === "ASK"
                    ? "Pregunta con contexto…"
                    : "Describe la acción que necesitas…"
                }
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              <div className="composerTools">
                <div>
                  <button
                    type="button"
                    className={`iconButton mic ${listening ? "recording" : ""}`}
                    disabled={loading}
                    aria-pressed={listening}
                    aria-label={
                      listening ? "Detener micrófono" : "Activar micrófono"
                    }
                    onClick={listen}
                  >
                    {listening ? <Square size={17} /> : <Mic size={18} />}
                  </button>
                  <span>
                    {listening
                      ? "Grabando… máximo 60 s"
                      : "Enter para enviar · Shift + Enter para nueva línea"}
                  </span>
                </div>
                {streaming ? (
                  <button
                    type="button"
                    className="quietButton"
                    onClick={() => chatRequest.current?.abort()}
                  >
                    Detener consulta
                  </button>
                ) : (
                  <button
                    aria-label="Enviar mensaje"
                    className="send"
                    disabled={!input.trim() || loading || !!deciding}
                  >
                    <Send size={17} />
                  </button>
                )}
              </div>
            </form>
            <p>
              Las citas permiten verificar pasajes. Una coincidencia no
              garantiza suficiencia semántica.
            </p>
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
          if (file) upload(file);
        }}
      />
      {inspected && (
        <Inspector
          title={inspected.filename}
          subtitle={
            inspected.page
              ? `Página ${inspected.page} · Fragmento #${inspected.chunk_id}`
              : `Sin páginas fiables · Fragmento #${inspected.chunk_id}`
          }
          onClose={() => setInspected(null)}
        >
          <div className="inspectorLabel">TEXTO RECUPERADO</div>
          <blockquote>{inspected.excerpt}</blockquote>
          <p className="footnote">
            Similitud: {inspected.score.toFixed(3)}. Es una medida de cercanía,
            no de certeza ni de aplicabilidad.
          </p>
          {inspected.document_id && (
            <button
              onClick={() =>
                inspectDocument({
                  id: inspected.document_id!,
                  filename: inspected.filename,
                } as DocumentItem)
              }
            >
              Ver fragmentos del documento <ArrowRightIcon />
            </button>
          )}
        </Inspector>
      )}
      {inspectDoc && (
        <Inspector
          title={inspectDoc.filename}
          subtitle="Texto conservado · solo workspace actual"
          onClose={() => {
            setInspectDoc(null);
            setChunkPage(null);
          }}
        >
          {inspectBusy ? (
            <p role="status">Cargando fragmentos…</p>
          ) : inspectError ? (
            <p role="alert">{inspectError}</p>
          ) : (
            <>
              {chunkPage?.chunks.map((c) => (
                <section className="chunkBlock" key={c.id}>
                  <span className="inspectorLabel">
                    FRAGMENTO {c.index + 1} ·{" "}
                    {c.page ? `PÁGINA ${c.page}` : "SIN PAGINACIÓN"}
                  </span>
                  <blockquote>{c.content}</blockquote>
                </section>
              ))}
              {chunkPage?.total === 0 && (
                <EmptyState title="Sin fragmentos conservados">
                  Este documento no contiene texto indexado. Revisa el error de
                  indexación y vuelve a subir un archivo válido.
                </EmptyState>
              )}
              {chunkPage && chunkPage.total > 0 && (
                <div className="pagination">
                  <button
                    disabled={chunkPage.offset === 0}
                    onClick={() =>
                      inspectDocument(
                        inspectDoc,
                        Math.max(0, chunkPage.offset - 25),
                      )
                    }
                  >
                    Anterior
                  </button>
                  <span>
                    {chunkPage.offset + 1}–
                    {Math.min(chunkPage.offset + 25, chunkPage.total)} de{" "}
                    {chunkPage.total}
                  </span>
                  <button
                    disabled={chunkPage.offset + 25 >= chunkPage.total}
                    onClick={() =>
                      inspectDocument(inspectDoc, chunkPage.offset + 25)
                    }
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
function ArrowRightIcon() {
  return <ArrowUpRight size={16} />;
}
