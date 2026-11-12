"use client";

import { useCallback, useSyncExternalStore } from "react";

export type ThemePreference = "system" | "light" | "dark";
const KEY = "mazmi-theme";
/** MAZMI is a dark interface; light and the OS preference remain an explicit choice. */
export const DEFAULT: ThemePreference = "dark";
const listeners = new Set<() => void>();

function read(): ThemePreference {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" || value === "system" ? value : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

/** Apply the stored preference (dark unless chosen otherwise); "system" defers to the OS. */
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
    () => DEFAULT,
  );
  const set = useCallback((value: ThemePreference) => {
    try {
      if (value === DEFAULT) window.localStorage.removeItem(KEY);
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
