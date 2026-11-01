// SPDX-License-Identifier: AGPL-3.0-or-later
// `prefers-reduced-motion` and page visibility as React state (render loop pause, NFR-U3).
import { useSyncExternalStore } from "react";

const REDUCED = "(prefers-reduced-motion: reduce)";

function media(): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(REDUCED) : null;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (listener) => {
      const query = media();
      query?.addEventListener("change", listener);
      return () => query?.removeEventListener("change", listener);
    },
    () => media()?.matches ?? false,
  );
}

export function usePageVisible(): boolean {
  return useSyncExternalStore(
    (listener) => {
      document.addEventListener("visibilitychange", listener);
      return () => document.removeEventListener("visibilitychange", listener);
    },
    () => !document.hidden,
  );
}
