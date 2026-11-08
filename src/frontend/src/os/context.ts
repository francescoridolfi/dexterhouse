// SPDX-License-Identifier: AGPL-3.0-or-later
import { createContext, useContext } from "react";
import { useStore } from "zustand";

import type { WindowState, WindowStore } from "./windowStore.ts";

export const WindowStoreContext = createContext<WindowStore | null>(null);

export function useWindows<T>(selector: (state: WindowState) => T): T {
  const store = useContext(WindowStoreContext);
  if (!store) throw new Error("useWindows outside <Desktop>");
  return useStore(store, selector);
}

export function useWindowStore(): WindowStore {
  const store = useContext(WindowStoreContext);
  if (!store) throw new Error("useWindowStore outside <Desktop>");
  return store;
}
