"use client";
import { useState } from "react";
import { Archive, ChevronDown, Menu, Pencil, Plus, Volume2, VolumeX } from "lucide-react";
import { RobotMark } from "../brand/robot-mark";

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

/** No chrome: the brand and where you are on the left, a few quiet actions on the right. */
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
    <header className="topbar">
      <button
        className="iconButton menuToggle"
        aria-expanded={menuOpen}
        aria-controls="workspace-panel"
        aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
        onClick={onMenu}
      >
        <Menu size={20} strokeWidth={1.75} />
      </button>
      <span className="topBrand" aria-hidden="true">
        <span className="brandTile">
          <RobotMark size={20} />
        </span>
        <b>MAZMI</b>
      </span>
      <div className="breadcrumb">
        <button
          className="crumbWorkspace"
          aria-expanded={menuOpen}
          aria-controls="workspace-panel"
          aria-label={`Workspace ${workspaceName}: cambiar o ver historial`}
          onClick={onMenu}
        >
          <span>{workspaceName}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
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
              title="Renombrar"
              disabled={locked}
              onClick={() => setEditing(true)}
            >
              <Pencil size={16} strokeWidth={1.75} />
            </button>
            <button
              className="iconButton"
              aria-label="Archivar conversación"
              title="Archivar"
              disabled={locked}
              onClick={() => void onArchive()}
            >
              <Archive size={16} strokeWidth={1.75} />
            </button>
          </>
        )}
        {isCopilot && (
          <button
            className={`iconButton voice ${speechEnabled ? "on" : ""}`}
            aria-pressed={speechEnabled}
            aria-label="Leer respuestas en voz alta"
            title="Leer respuestas en voz alta"
            onClick={onSpeech}
          >
            {speechEnabled ? <Volume2 size={17} strokeWidth={1.75} /> : <VolumeX size={17} strokeWidth={1.75} />}
          </button>
        )}
        <button className="ghost newQuery" disabled={locked} onClick={onNewConversation}>
          <Plus size={16} aria-hidden="true" /> <span>Nueva consulta</span>
        </button>
      </div>
    </header>
  );
}
