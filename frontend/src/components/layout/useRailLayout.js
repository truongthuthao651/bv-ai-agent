import { useCallback, useEffect, useRef, useState } from "react";

export const RAIL_DEFAULT_WIDTH = 264;
export const RAIL_MIN_WIDTH = 200;
export const RAIL_MAX_WIDTH = 480;

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n));
}

function readStored(storageKey) {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeStored(storageKey, data) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(data));
  } catch {
    /* quota / private mode */
  }
}

/** Persisted sidebar width + collapsed state for chat/admin rails. */
export function useRailLayout(storageKey) {
  const stored = readStored(storageKey);
  const [width, setWidth] = useState(() => {
    const w = stored?.width;
    return typeof w === "number" ? clamp(w, RAIL_MIN_WIDTH, RAIL_MAX_WIDTH) : RAIL_DEFAULT_WIDTH;
  });
  const [collapsed, setCollapsed] = useState(() => Boolean(stored?.collapsed));
  const widthRef = useRef(width);
  widthRef.current = width;

  useEffect(() => {
    writeStored(storageKey, { width, collapsed });
  }, [storageKey, width, collapsed]);

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);
  const expand = useCallback(() => setCollapsed(false), []);
  const collapse = useCallback(() => setCollapsed(true), []);

  const startResize = useCallback((clientX) => {
    const startX = clientX;
    const startWidth = widthRef.current;

    function onMove(ev) {
      const next = clamp(startWidth + ev.clientX - startX, RAIL_MIN_WIDTH, RAIL_MAX_WIDTH);
      setWidth(next);
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const onResizePointerDown = useCallback(
    (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      startResize(e.clientX);
    },
    [startResize],
  );

  return { width, collapsed, toggleCollapsed, expand, collapse, onResizePointerDown };
}
