"use client";
import { memo, useEffect, useLayoutEffect, useRef, useState, type SyntheticEvent } from "react";
import {
  History,
  LayoutGrid,
  LibraryBig,
  LogOut,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { Conversation, View } from "../product-types";
import type { Account } from "../account";
import { RobotMark } from "../brand/robot-mark";

/** Order of the rail: the conversation first, then knowledge, then the workspace tools. */
export const NAV_ITEMS = [
  { view: "Copilot", label: "Copilot", icon: MessagesSquare },
  { view: "Knowledge", label: "Knowledge", icon: LibraryBig },
  { view: "Workspace", label: "Workspace", icon: LayoutGrid },
  { view: "Approvals", label: "Aprobaciones", icon: ShieldCheck },
  { view: "Activity", label: "Actividad", icon: History },
  { view: "Settings", label: "Configuración", icon: SlidersHorizontal },
] as const;

const ICON = { size: 20, strokeWidth: 1.75 } as const;
const TIP_DELAY = 420;
const TIP_WARM = 450;

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
  onToggle: () => void;
  onClose: () => void;
  onWorkspace: (id: string) => void;
  onConversation: (id: string) => void;
  onNewConversation: () => void;
  onSignOut: () => void;
};

/**
 * A floating charcoal rail with icons only, and a panel opened on purpose (never on hover)
 * that shows section names, the workspace, the conversation history and the account.
 */
export const Sidebar = memo(function Sidebar(props: Props) {
  const { view, open, pendingCount, locked, onView, onToggle, onNewConversation } = props;
  const rail = useRef<HTMLElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const indicator = useRef<HTMLSpanElement>(null);
  const tips = useTooltip(rail);

  // One glass capsule travels to the active section (transform only). Layout changes
  // (resize, rail becoming a tab bar) reposition it instantly; only navigation animates.
  useLayoutEffect(() => {
    const nav = navRef.current;
    const pill = indicator.current;
    if (!nav || !pill) return;
    const place = (animate: boolean) => {
      const active = nav.querySelector<HTMLElement>(".railItem.active");
      pill.dataset.ready = animate ? "true" : "false";
      if (!active) {
        pill.style.opacity = "0";
        return;
      }
      pill.style.opacity = "1";
      pill.style.width = `${active.offsetWidth}px`;
      pill.style.height = `${active.offsetHeight}px`;
      pill.style.transform = `translate3d(${active.offsetLeft}px, ${active.offsetTop}px, 0)`;
    };
    place(pill.dataset.section !== undefined && pill.dataset.section !== view);
    pill.dataset.section = view;
    if (typeof ResizeObserver === "undefined") return;
    let size = `${nav.clientWidth}x${nav.clientHeight}`;
    const observer = new ResizeObserver(() => {
      const next = `${nav.clientWidth}x${nav.clientHeight}`;
      if (next === size) return;
      size = next;
      place(false);
    });
    observer.observe(nav);
    return () => observer.disconnect();
  }, [view]);

  return (
    <>
      <aside ref={rail} className="rail" aria-label="Navegación principal">
        <button
          className="railNew"
          aria-label="Nueva conversación"
          disabled={locked}
          onClick={onNewConversation}
          {...tips.bind("Nueva conversación")}
        >
          <Plus size={20} strokeWidth={2} aria-hidden="true" />
        </button>
        <nav ref={navRef} className="railNav" aria-label="Secciones">
          <span ref={indicator} className="railIndicator" aria-hidden="true" />
          {NAV_ITEMS.map(({ view: next, label, icon: Icon }) => (
            <button
              key={next}
              className={`railItem ${view === next ? "active" : ""}`}
              aria-current={view === next ? "page" : undefined}
              aria-describedby={next === "Approvals" && pendingCount > 0 ? "pending-count" : undefined}
              onClick={() => onView(next)}
              {...tips.bind(label)}
            >
              <Icon {...ICON} aria-hidden="true" />
              <span className="srOnly">{label}</span>
              {next === "Approvals" && pendingCount > 0 && (
                <b className="railCount" aria-hidden="true">
                  {pendingCount}
                </b>
              )}
            </button>
          ))}
        </nav>
        <div className="railFoot">
          <button
            className="railItem"
            aria-label={open ? "Ocultar panel" : "Mostrar nombres e historial"}
            aria-expanded={open}
            aria-controls="workspace-panel"
            onClick={onToggle}
            {...tips.bind(open ? "Ocultar panel" : "Nombres e historial")}
          >
            {open ? <PanelLeftClose {...ICON} aria-hidden="true" /> : <PanelLeftOpen {...ICON} aria-hidden="true" />}
          </button>
          <button
            className="railAvatar"
            aria-label={`Cuenta: ${props.account.email}`}
            aria-expanded={open}
            aria-controls="workspace-panel"
            onClick={onToggle}
            {...tips.bind(props.account.email)}
          >
            {props.account.email[0].toUpperCase()}
          </button>
        </div>
        <span id="pending-count" className="srOnly">
          {pendingCount > 0 ? `${pendingCount} pendientes de decidir` : ""}
        </span>
        <span
          className="railTip"
          aria-hidden="true"
          data-visible={tips.state.visible}
          style={{ transform: `translate3d(0, ${tips.state.y}px, 0)` }}
        >
          <span>{tips.state.label}</span>
        </span>
      </aside>
      <WorkspacePanel {...props} />
    </>
  );
});

function WorkspacePanel({
  account,
  workspaceName,
  view,
  open,
  pendingCount,
  conversations,
  conversationId,
  locked,
  onView,
  onClose,
  onWorkspace,
  onConversation,
  onNewConversation,
  onSignOut,
}: Props) {
  const panel = useRef<HTMLDivElement>(null);
  // Opening moves focus into the panel; Escape closes it and focus returns to the opener.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>(".panelClose")?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      if (previous?.isConnected) previous.focus();
    };
  }, [open, onClose]);
  return (
    <>
      <div className="panelScrim" data-open={open} aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        id="workspace-panel"
        className="workspacePanel"
        data-open={open}
        role="dialog"
        aria-modal="false"
        aria-label="Workspace, secciones e historial"
        aria-hidden={!open}
        inert={!open}
      >
        <header className="panelHeader">
          <span className="brandTile" aria-hidden="true">
            <RobotMark size={22} />
          </span>
          <div>
            <b>MAZMI</b>
            <small>Ops Copilot</small>
          </div>
          <button className="iconButton small panelClose" aria-label="Ocultar panel" onClick={onClose}>
            <PanelLeftClose size={17} strokeWidth={1.75} />
          </button>
        </header>
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
        <nav className="panelNav" aria-label="Secciones con nombre">
          {NAV_ITEMS.map(({ view: next, label, icon: Icon }) => (
            <button
              key={next}
              className={`panelLink ${view === next ? "active" : ""}`}
              aria-current={view === next ? "page" : undefined}
              onClick={() => onView(next)}
            >
              <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
              <span>{label}</span>
              {next === "Approvals" && pendingCount > 0 && <b className="panelCount">{pendingCount}</b>}
            </button>
          ))}
        </nav>
        <div className="conversationList">
          <div className="sectionTitle">
            <span>Conversaciones</span>
            <button
              className="iconButton small"
              aria-label="Empezar una conversación nueva"
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
        <footer className="panelFooter">
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
        </footer>
      </div>
    </>
  );
}

/**
 * One tooltip for the whole rail. The first one waits (no flicker while the pointer passes
 * by); once one is showing, moving to a neighbour switches instantly, without animation.
 * Keyboard focus shows it at once. Names never depend on it: every button has a label.
 */
function useTooltip(rail: React.RefObject<HTMLElement | null>) {
  const [state, setState] = useState({ label: "", y: 0, visible: false });
  const visible = useRef(false);
  const warmUntil = useRef(0);
  const timer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );
  const clear = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const show = (e: SyntheticEvent<HTMLElement>, label: string, immediate: boolean) => {
    const root = rail.current;
    if (!root || window.matchMedia?.("(max-width: 767px)")?.matches) return;
    const box = e.currentTarget.getBoundingClientRect();
    const y = box.top - root.getBoundingClientRect().top + box.height / 2;
    clear();
    const reveal = () => {
      visible.current = true;
      setState({ label, y, visible: true });
    };
    if (immediate || visible.current || performance.now() < warmUntil.current) reveal();
    else timer.current = window.setTimeout(reveal, TIP_DELAY);
  };
  const hide = () => {
    clear();
    if (visible.current) warmUntil.current = performance.now() + TIP_WARM;
    visible.current = false;
    setState((s) => (s.visible ? { ...s, visible: false } : s));
  };
  return {
    state,
    bind: (label: string) => ({
      onPointerEnter: (e: React.PointerEvent<HTMLElement>) => e.pointerType === "mouse" && show(e, label, false),
      onPointerLeave: hide,
      onFocus: (e: React.FocusEvent<HTMLElement>) => {
        let keyboard = false;
        try {
          keyboard = e.currentTarget.matches(":focus-visible");
        } catch {
          keyboard = false;
        }
        if (keyboard) show(e, label, true);
      },
      onBlur: hide,
      onPointerDown: hide,
    }),
  };
}
