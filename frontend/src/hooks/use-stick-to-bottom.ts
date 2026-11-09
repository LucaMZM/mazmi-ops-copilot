"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

const THRESHOLD_PX = 120;

/**
 * Follow new content only while the reader is already at the bottom. Scrolling up to
 * read earlier messages pauses following and exposes a "jump to latest" affordance.
 */
export function useStickToBottom(
  container: RefObject<HTMLElement | null>,
  anchor: RefObject<HTMLElement | null>,
  signal: unknown,
) {
  const following = useRef(true);
  const [hasUnseen, setHasUnseen] = useState(false);

  const onScroll = useCallback(() => {
    const el = container.current;
    if (!el) return;
    following.current = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD_PX;
    if (following.current) setHasUnseen(false);
  }, [container]);

  const jump = useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      following.current = true;
      setHasUnseen(false);
      anchor.current?.scrollIntoView({ behavior, block: "end" });
    },
    [anchor],
  );

  useEffect(() => {
    if (following.current) {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      anchor.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
    } else {
      setHasUnseen(true);
    }
  }, [signal, anchor]);

  return { onScroll, jump, hasUnseen, follow: () => (following.current = true) };
}
