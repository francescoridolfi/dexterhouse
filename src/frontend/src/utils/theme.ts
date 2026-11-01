// SPDX-License-Identifier: AGPL-3.0-or-later
// Dark mode: `prefers-color-scheme` by default, header toggle remembered in localStorage.
import { useSyncExternalStore } from "react";

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "dh.theme";
const listeners = new Set<() => void>();

function stored(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemDark(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false;
}

export function resolvedDark(choice: ThemeChoice = stored()): boolean {
  return choice === "dark" || (choice === "system" && systemDark());
}

export function applyTheme(choice: ThemeChoice = stored()): void {
  document.documentElement.classList.toggle("dark", resolvedDark(choice));
}

export function setTheme(choice: ThemeChoice): void {
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  applyTheme(choice);
  listeners.forEach((listener) => listener());
}

export function useDarkMode(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => resolvedDark(),
  );
}
