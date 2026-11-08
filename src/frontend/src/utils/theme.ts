// SPDX-License-Identifier: AGPL-3.0-or-later
// DexterOS is dark only (liquid glass): the 3D office keeps reading its dark palette.

export function resolvedDark(): boolean {
  return true;
}

export function applyTheme(): void {
  document.documentElement.classList.add("dark");
}

export function useDarkMode(): boolean {
  return true;
}
