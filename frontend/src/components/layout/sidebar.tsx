"use client";
import { memo } from "react";
import {
  Bot,
  FileText,
  History,
  LayoutGrid,
  LogOut,
  Plus,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import type { Conversation, View } from "../product-types";
import type { Account } from "../account";

export const NAV_ITEMS = [
  { view: "Workspace", label: "Workspace", icon: LayoutGrid },
  { view: "Copilot", label: "Copilot", icon: Bot },
  { view: "Knowledge", label: "Knowledge", icon: FileText },
  { view: "Approvals", label: "Aprobaciones", icon: ShieldCheck },
  { view: "Activity", label: "Actividad", icon: History },
  { view: "Settings", label: "Configuración", icon: Settings2 },
] as const;

type Props = {
  account: Account;
  workspaceName: string;
  view: View;
  open: boolean;
  pendingCount: number;
  conversations: Conversation[];
  conversationId: string | null;
  locked: boolean;
  onView: (view: View) => void;
  onWorkspace: (id: string) => void;
  onConversation: (id: string) => void;
  onNewConversation: () => void;
  onSignOut: () => void;
};

export const Sidebar = memo(function Sidebar({
  account,
  workspaceName,
  view,
  open,
  pendingCount,
  conversations,
  conversationId,
  locked,
  onView,
  onWorkspace,
  onConversation,
  onNewConversation,
  onSignOut,
}: Props) {
  return (
    <aside className={`sidebar glass ${open ? "open" : ""}`} aria-label="Navegación del workspace">
      <div className="brand">
        <span className="brandmark" aria-hidden="true">
          M
        </span>
        <div>
          <b>MAZMI</b>
          <small>Ops Copilot</small>
        </div>
      </div>
      <label className="workspacePicker">
        <span className="workspaceMonogram" aria-hidden="true">
          {workspaceName[0]}
        </span>
        <span className="pickerText">
          <small>Espacio de trabajo</small>
          <select
            aria-label="Workspace"
            disabled={locked}
            value={account.workspace_id}
            onChange={(e) => onWorkspace(e.target.value)}
          >
            {account.workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </span>
      </label>
      <nav className="primaryNav" aria-label="Secciones">
        {NAV_ITEMS.map(({ view: next, label, icon: Icon }) => (
          <button
            key={next}
            className={`nav ${view === next ? "active" : ""}`}
            aria-current={view === next ? "page" : undefined}
            onClick={() => onView(next)}
          >
            <Icon size={18} aria-hidden="true" />
            <span className="navLabel">{label}</span>
            {next === "Approvals" && pendingCount > 0 && (
              <b className="navCount" aria-label={`${pendingCount} pendientes`}>
                {pendingCount}
              </b>
            )}
          </button>
        ))}
      </nav>
      <div className="conversationList">
        <div className="sectionTitle">
          <span>Conversaciones</span>
          <button
            className="iconButton small"
            aria-label="Nueva conversación"
            disabled={locked}
            onClick={onNewConversation}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="conversationScroll">
          {conversations.map((c) => (
            <button
              className={`conversationLink ${conversationId === c.id ? "active" : ""}`}
              aria-current={conversationId === c.id ? "true" : undefined}
              disabled={locked}
              key={c.id}
              onClick={() => onConversation(c.id)}
            >
              {c.title}
            </button>
          ))}
          {!conversations.length && <p className="muted small">Tus consultas quedarán guardadas aquí.</p>}
        </div>
      </div>
      <div className="sidebarFooter">
        <p className="scopeNote">
          <ShieldCheck size={14} aria-hidden="true" /> Datos del workspace actual
        </p>
        <div className="accountRow">
          <span className="accountAvatar" aria-hidden="true">
            {account.email[0].toUpperCase()}
          </span>
          <span className="accountEmail">{account.email}</span>
          <button className="iconButton small" aria-label="Cerrar sesión" disabled={locked} onClick={onSignOut}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
});
