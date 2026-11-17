"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Diagnostic mode is a per-browser opt-in for people who debug answers. It only reveals a
 * button; what that button shows is still authorized by the server per workspace.
 */
const KEY = "mazmi-diagnostics";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function useDiagnostics(): [boolean, (on: boolean) => void] {
  const enabled = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    () => false,
  );
  const set = useCallback((on: boolean) => {
    try {
      if (on) window.localStorage.setItem(KEY, "on");
      else window.localStorage.removeItem(KEY);
    } catch {
      // Blocked storage: the change still applies until the page reloads.
    }
    listeners.forEach((listener) => listener());
  }, []);
  return [enabled, set];
}
