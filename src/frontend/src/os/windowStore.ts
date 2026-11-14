// SPDX-License-Identifier: AGPL-3.0-or-later
// Window manager state. One store per <Desktop> (tests mount many). The URL always mirrors
// the focused window: `visit(path)` is called on every location change. Windows are keyed
// by `windowKey(path)`: the app, or `app:instance` for apps with one window per project.
import { createStore } from "zustand/vanilla";

import { APPS, type AppId, appFor, windowKey } from "./apps.ts";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Win {
  id: string;
  app: AppId;
  path: string;
  rect: Rect;
  minimized: boolean;
  maximized: boolean;
  /** Closed when the focus moves to another window (wizards, pickers). */
  transient: boolean;
}

export interface WindowState {
  windows: Partial<Record<string, Win>>;
  /** Stacking order (window ids), bottom → top. */
  order: string[];
  focused: string | null;
  visit: (path: string) => void;
  focus: (id: string) => void;
  close: (id: string) => void;
  minimize: (id: string) => void;
  toggleMaximize: (id: string) => void;
  setRect: (id: string, rect: Rect, persist?: boolean) => void;
  /** The window that should get the focus next (topmost visible), if any. */
  topmost: (except?: string) => Win | null;
  /** The most recently raised window of `app`. */
  latest: (app: AppId) => Win | null;
}

export const MENUBAR_H = 32;
export const DOCK_RESERVE = 92;
export const MIN_W = 380;
export const MIN_H = 260;
const KEY = "dh.os.geometry";
const CASCADE = 28;

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

/** `siblings`: open windows of the same app, so a second project window does not cover the first. */
function initialRect(app: AppId, cascade: number, siblings: number): Rect {
  const saved = loadGeometry()[app];
  const shift = siblings * CASCADE;
  if (saved) return clampRect({ ...saved, x: saved.x + shift, y: saved.y + shift });
  const vp = viewport();
  const { size } = APPS[app];
  const avail = vp.h - MENUBAR_H - DOCK_RESERVE;
  const w = Math.min(size.w, vp.w - 48);
  const h = Math.min(size.h, avail - 24);
  const step = (cascade % 6) * CASCADE + shift;
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
      const id = windowKey(next);
      const { windows, order, focused } = get();
      const rest = { ...windows };
      let stack = order;
      if (focused && focused !== id && rest[focused]?.transient) {
        delete rest[focused];
        stack = stack.filter((key) => key !== focused);
      }
      if (id === null) {
        set({ windows: rest, order: stack, focused: null });
        return;
      }
      const app = appFor(next) as AppId;
      const current = rest[id];
      const siblings = stack.filter((key) => rest[key]?.app === app).length;
      rest[id] = current
        ? { ...current, path: next, minimized: false }
        : {
            id,
            app,
            path: next,
            rect: initialRect(app, stack.length, siblings),
            minimized: false,
            maximized: false,
            transient: Boolean(APPS[app].transient) || (!!APPS[app].instance && id === app),
          };
      set({ windows: rest, order: [...stack.filter((key) => key !== id), id], focused: id });
    },

    focus: (id) =>
      set(({ order, windows }) => {
        const win = windows[id];
        if (!win) return {};
        return {
          order: [...order.filter((key) => key !== id), id],
          focused: id,
          windows: { ...windows, [id]: { ...win, minimized: false } },
        };
      }),

    close: (id) =>
      set(({ windows, order, focused }) => {
        const rest = { ...windows };
        delete rest[id];
        return {
          windows: rest,
          order: order.filter((key) => key !== id),
          focused: focused === id ? null : focused,
        };
      }),

    minimize: (id) =>
      set(({ windows, focused }) => {
        const win = windows[id];
        if (!win) return {};
        return {
          windows: { ...windows, [id]: { ...win, minimized: true } },
          focused: focused === id ? null : focused,
        };
      }),

    toggleMaximize: (id) =>
      set(({ windows }) => {
        const win = windows[id];
        return win ? { windows: { ...windows, [id]: { ...win, maximized: !win.maximized } } } : {};
      }),

    setRect: (id, rect, persist = false) => {
      const win = get().windows[id];
      if (!win) return;
      set({ windows: { ...get().windows, [id]: { ...win, rect, maximized: false } } });
      if (persist) saveGeometry(win.app, rect);
    },

    topmost: (except) => {
      const { order, windows } = get();
      for (let i = order.length - 1; i >= 0; i -= 1) {
        const win = windows[order[i]!];
        if (win && !win.minimized && win.id !== except) return win;
      }
      return null;
    },

    latest: (app) => {
      const { order, windows } = get();
      for (let i = order.length - 1; i >= 0; i -= 1) {
        const win = windows[order[i]!];
        if (win?.app === app) return win;
      }
      return null;
    },
  }));
  store.getState().visit(path);
  return store;
}

export type WindowStore = ReturnType<typeof createWindowStore>;
