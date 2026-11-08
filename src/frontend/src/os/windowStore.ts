// SPDX-License-Identifier: AGPL-3.0-or-later
// Window manager state. One store per <Desktop> (tests mount many). The URL always mirrors
// the focused window: `visit(path)` is called on every location change.
import { createStore } from "zustand/vanilla";

import { APPS, type AppId, appFor } from "./apps.ts";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Win {
  app: AppId;
  path: string;
  rect: Rect;
  minimized: boolean;
  maximized: boolean;
}

export interface WindowState {
  windows: Partial<Record<AppId, Win>>;
  /** Stacking order, bottom → top. */
  order: AppId[];
  focused: AppId | null;
  visit: (path: string) => void;
  focus: (app: AppId) => void;
  close: (app: AppId) => void;
  minimize: (app: AppId) => void;
  toggleMaximize: (app: AppId) => void;
  setRect: (app: AppId, rect: Rect, persist?: boolean) => void;
  /** The window that should get the focus next (topmost visible), if any. */
  topmost: (except?: AppId) => Win | null;
}

export const MENUBAR_H = 32;
export const DOCK_RESERVE = 92;
export const MIN_W = 380;
export const MIN_H = 260;
const KEY = "dh.os.geometry";

function loadGeometry(): Partial<Record<AppId, Rect>> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Record<AppId, Rect>>;
  } catch {
    return {};
  }
}

function saveGeometry(app: AppId, rect: Rect) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...loadGeometry(), [app]: rect }));
  } catch {
    // storage unavailable: the layout lasts for this page only
  }
}

function viewport() {
  return {
    w: typeof window === "undefined" ? 1280 : window.innerWidth,
    h: typeof window === "undefined" ? 800 : window.innerHeight,
  };
}

export function clampRect(rect: Rect): Rect {
  const vp = viewport();
  const w = Math.max(MIN_W, Math.min(rect.w, vp.w - 16));
  const h = Math.max(MIN_H, Math.min(rect.h, vp.h - MENUBAR_H - 16));
  return {
    w,
    h,
    x: Math.min(Math.max(rect.x, 8 - w + 120), vp.w - 120),
    y: Math.min(Math.max(rect.y, MENUBAR_H + 4), vp.h - 60),
  };
}

function initialRect(app: AppId, cascade: number): Rect {
  const saved = loadGeometry()[app];
  if (saved) return clampRect(saved);
  const vp = viewport();
  const { size } = APPS[app];
  const avail = vp.h - MENUBAR_H - DOCK_RESERVE;
  const w = Math.min(size.w, vp.w - 48);
  const h = Math.min(size.h, avail - 24);
  const step = (cascade % 6) * 28;
  return clampRect({
    w,
    h,
    x: Math.round((vp.w - w) / 2) + step - 56,
    y: MENUBAR_H + Math.max(12, Math.round((avail - h) / 2) - 8) + step,
  });
}

export function createWindowStore(path: string) {
  const store = createStore<WindowState>()((set, get) => ({
    windows: {},
    order: [],
    focused: null,

    visit: (next) => {
      const app = appFor(next);
      const { windows, order, focused } = get();
      const rest = { ...windows };
      let stack = order;
      if (focused && focused !== app && APPS[focused].transient) {
        delete rest[focused];
        stack = stack.filter((id) => id !== focused);
      }
      if (app === null) {
        set({ windows: rest, order: stack, focused: null });
        return;
      }
      const current = rest[app];
      rest[app] = current
        ? { ...current, path: next, minimized: false }
        : {
            app,
            path: next,
            rect: initialRect(app, stack.length),
            minimized: false,
            maximized: false,
          };
      set({ windows: rest, order: [...stack.filter((id) => id !== app), app], focused: app });
    },

    focus: (app) =>
      set(({ order, windows }) => {
        const win = windows[app];
        if (!win) return {};
        return {
          order: [...order.filter((id) => id !== app), app],
          focused: app,
          windows: { ...windows, [app]: { ...win, minimized: false } },
        };
      }),

    close: (app) =>
      set(({ windows, order, focused }) => {
        const rest = { ...windows };
        delete rest[app];
        return {
          windows: rest,
          order: order.filter((id) => id !== app),
          focused: focused === app ? null : focused,
        };
      }),

    minimize: (app) =>
      set(({ windows, focused }) => {
        const win = windows[app];
        if (!win) return {};
        return {
          windows: { ...windows, [app]: { ...win, minimized: true } },
          focused: focused === app ? null : focused,
        };
      }),

    toggleMaximize: (app) =>
      set(({ windows }) => {
        const win = windows[app];
        return win ? { windows: { ...windows, [app]: { ...win, maximized: !win.maximized } } } : {};
      }),

    setRect: (app, rect, persist = false) => {
      const win = get().windows[app];
      if (!win) return;
      set({ windows: { ...get().windows, [app]: { ...win, rect, maximized: false } } });
      if (persist) saveGeometry(app, rect);
    },

    topmost: (except) => {
      const { order, windows } = get();
      for (let i = order.length - 1; i >= 0; i -= 1) {
        const win = windows[order[i]!];
        if (win && !win.minimized && win.app !== except) return win;
      }
      return null;
    },
  }));
  store.getState().visit(path);
  return store;
}

export type WindowStore = ReturnType<typeof createWindowStore>;
