"use client";
import { useState } from "react";
import { Archive, Menu, Pencil, Plus, Volume2, VolumeX, X } from "lucide-react";

type Props = {
  workspaceName: string;
  title: string;
  menuOpen: boolean;
  onMenu: () => void;
  isCopilot: boolean;
  conversationTitle: string | null;
  locked: boolean;
  speechEnabled: boolean;
  onSpeech: () => void;
  onNewConversation: () => void;
  onRename: (title: string) => Promise<void>;
  onArchive: () => Promise<void>;
};

export function Topbar({
  workspaceName,
  title,
  menuOpen,
  onMenu,
  isCopilot,
  conversationTitle,
  locked,
  speechEnabled,
  onSpeech,
  onNewConversation,
  onRename,
  onArchive,
}: Props) {
  const [editing, setEditing] = useState(false);
  return (
    <header className="topbar glass">
      <button
        className="iconButton menuToggle"
        aria-expanded={menuOpen}
        aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
        onClick={onMenu}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <div className="breadcrumb">
        <span className="crumbWorkspace">{workspaceName}</span>
        <span className="crumbSeparator" aria-hidden="true">
          /
        </span>
        <h1>{title}</h1>
        {isCopilot && conversationTitle && !editing && (
          <span className="conversationTitle" title={conversationTitle}>
            {conversationTitle}
          </span>
        )}
        {isCopilot && conversationTitle && editing && (
          <form
            className="renameForm"
            onSubmit={async (e) => {
              e.preventDefault();
              const value = String(new FormData(e.currentTarget).get("title") ?? "").trim();
              if (value) await onRename(value);
              setEditing(false);
            }}
          >
            <input
              name="title"
              aria-label="Nuevo título de la conversación"
              defaultValue={conversationTitle}
              maxLength={120}
              autoFocus
              onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
            />
            <button className="ghost small">Guardar</button>
          </form>
        )}
      </div>
      <div className="headerActions">
        {isCopilot && conversationTitle && !editing && (
          <>
            <button
              className="iconButton"
              aria-label="Renombrar conversación"
              disabled={locked}
              onClick={() => setEditing(true)}
            >
              <Pencil size={16} />
            </button>
            <button
              className="iconButton"
              aria-label="Archivar conversación"
              disabled={locked}
              onClick={() => void onArchive()}
            >
              <Archive size={16} />
            </button>
          </>
        )}
        {isCopilot && (
          <button
            className={`iconButton voice ${speechEnabled ? "on" : ""}`}
            aria-pressed={speechEnabled}
            aria-label="Leer respuestas en voz alta"
            onClick={onSpeech}
          >
            {speechEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
          </button>
        )}
        <button className="ghost newQuery" disabled={locked} onClick={onNewConversation}>
          <Plus size={16} aria-hidden="true" /> <span>Nueva consulta</span>
        </button>
      </div>
    </header>
  );
}
