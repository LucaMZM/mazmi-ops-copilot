"use client";

import { useCallback, useSyncExternalStore } from "react";

export type ThemePreference = "system" | "light" | "dark";
const KEY = "mazmi-theme";
const listeners = new Set<() => void>();

function read(): ThemePreference {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

/** Apply the stored preference; "system" defers to prefers-color-scheme in CSS. */
export function applyTheme(preference: ThemePreference = read()) {
  const root = document.documentElement;
  if (preference === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", preference);
}

export function useTheme(): [ThemePreference, (value: ThemePreference) => void] {
  const theme = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    () => "system" as ThemePreference,
  );
  const set = useCallback((value: ThemePreference) => {
    try {
      if (value === "system") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, value);
    } catch {
      // Storage may be blocked (private mode); the choice still applies to this page.
    }
    // A light/dark switch is an abrupt brightness jump: crossfade it where supported, except
    // with reduced motion. The change itself is synchronous either way.
    const swap = () => {
      applyTheme(value);
      listeners.forEach((listener) => listener());
    };
    const doc = document as Document & { startViewTransition?: (update: () => void) => unknown };
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (doc.startViewTransition && !reduce) doc.startViewTransition(swap);
    else swap();
  }, []);
  return [theme, set];
}
