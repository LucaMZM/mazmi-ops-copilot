"use client";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";

export type Command = {
  id: string;
  label: string;
  group: string;
  icon?: ReactNode;
  hint?: string;
  /** Extra words that should also find this command. */
  keywords?: string;
  disabled?: boolean;
  run: () => void;
};

const fold = (text: string) =>
  text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * ⌘K / Ctrl+K: one field that finds sections, actions and conversations. A combobox with a
 * listbox (WAI-ARIA pattern): focus stays in the field, arrows move the active option.
 */
export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const results = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return commands.filter((c) => {
      const haystack = fold(`${c.label} ${c.group} ${c.keywords ?? ""}`);
      return words.every((w) => haystack.includes(w));
    });
  }, [commands, query]);
  const current = Math.min(active, Math.max(0, results.length - 1));

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${current}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  const run = (command: Command | undefined) => {
    if (!command || command.disabled) return;
    onClose();
    command.run();
  };

  return (
    <div className="paletteBackdrop" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Paleta de comandos"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="paletteField">
          <Search size={17} strokeWidth={1.75} aria-hidden="true" />
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls={`${id}-list`}
            aria-activedescendant={results.length ? `${id}-${current}` : undefined}
            aria-autocomplete="list"
            aria-label="Buscar secciones, acciones o conversaciones"
            placeholder="Buscar secciones, acciones o conversaciones…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((current + 1) % Math.max(1, results.length));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((current - 1 + results.length) % Math.max(1, results.length));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(results[current]);
              } else if (e.key === "Escape") {
                e.preventDefault();
                onClose();
              } else if (e.key === "Tab") {
                e.preventDefault();
              }
            }}
          />
          <kbd>Esc</kbd>
        </div>
        <ul ref={list} id={`${id}-list`} role="listbox" aria-label="Resultados" className="paletteList">
          {results.map((command, i) => {
            const header = i === 0 || results[i - 1].group !== command.group;
            return (
              <li key={command.id} role="presentation">
                {header && (
                  <span className="paletteGroup" aria-hidden="true">
                    {command.group}
                  </span>
                )}
                <div
                  id={`${id}-${i}`}
                  data-index={i}
                  role="option"
                  aria-selected={i === current}
                  aria-disabled={command.disabled || undefined}
                  className={`paletteOption ${i === current ? "active" : ""}`}
                  onMouseMove={() => i !== current && setActive(i)}
                  onClick={() => run(command)}
                >
                  <span className="paletteIcon" aria-hidden="true">
                    {command.icon}
                  </span>
                  <span className="paletteLabel">{command.label}</span>
                  {command.hint && <span className="paletteHint">{command.hint}</span>}
                </div>
              </li>
            );
          })}
          {!results.length && <li className="paletteEmpty">Sin resultados para «{query}».</li>}
        </ul>
      </div>
    </div>
  );
}
