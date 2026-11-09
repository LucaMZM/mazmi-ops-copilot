"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, request } from "@/lib/api";
import type {
  Activity,
  Conversation,
  DocumentItem,
  PendingAction,
  SystemInfo,
} from "@/components/product-types";

type Resources = {
  documents: DocumentItem[];
  conversations: Conversation[];
  actions: PendingAction[];
  activity: Activity[];
};
export type ResourceName = keyof Resources | "system";

const PATHS: Record<ResourceName, string> = {
  documents: "/api/documents",
  conversations: "/api/conversations",
  actions: "/api/actions",
  activity: "/api/activity",
  system: "/api/system",
};

/**
 * Workspace-scoped server state. The parent remounts this per workspace (React key),
 * so nothing can leak between workspaces; inside one workspace, a per-resource
 * sequence number guarantees that a slow, older response never overwrites a newer one,
 * and responses arriving after unmount are ignored.
 */
export function useWorkspaceData() {
  const [data, setData] = useState<Resources>({
    documents: [],
    conversations: [],
    actions: [],
    activity: [],
  });
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const sequence = useRef<Record<ResourceName, number>>({
    documents: 0,
    conversations: 0,
    actions: 0,
    activity: 0,
    system: 0,
  });
  const alive = useRef(true);

  const apply = useCallback((name: ResourceName, value: unknown) => {
    if (name === "system") {
      const config = value as SystemInfo;
      if (config?.generation) setSystem(config);
      return;
    }
    setData((current) => ({ ...current, [name]: value }));
  }, []);

  const load = useCallback(
    async (name: ResourceName) => {
      const version = ++sequence.current[name];
      const value = await request<unknown>(PATHS[name]);
      if (alive.current && version === sequence.current[name]) apply(name, value);
    },
    [apply],
  );

  const refresh = useCallback(
    async (...names: ResourceName[]) => {
      await Promise.all(names.map(load));
    },
    [load],
  );

  useEffect(() => {
    alive.current = true;
    const names: ResourceName[] = ["documents", "conversations", "system", "actions", "activity"];
    Promise.allSettled(names.map(load)).then((results) => {
      if (!alive.current) return;
      const failure = results.find((r) => r.status === "rejected");
      if (failure?.status === "rejected") setLoadError(errorMessage(failure.reason));
      setInitialLoading(false);
    });
    return () => {
      alive.current = false;
    };
  }, [load]);

  const setActions = useCallback(
    (update: (current: PendingAction[]) => PendingAction[]) =>
      setData((current) => ({ ...current, actions: update(current.actions) })),
    [],
  );
  const setConversations = useCallback(
    (update: (current: Conversation[]) => Conversation[]) =>
      setData((current) => ({ ...current, conversations: update(current.conversations) })),
    [],
  );

  return {
    ...data,
    system,
    setSystem,
    setActions,
    setConversations,
    initialLoading,
    loadError,
    refresh,
  };
}
