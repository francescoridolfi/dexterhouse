// SPDX-License-Identifier: AGPL-3.0-or-later
// DexterOS: wallpaper, widgets, app windows, menu bar and dock. The browser URL is the path
// of the focused window: navigating opens or focuses the window of that app, and focusing,
// minimizing or closing a window navigates to whatever window ends up on top ("/" = desktop).
import { useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/endpoints.ts";
import { APPS, type AppId } from "./apps.ts";
import { WindowStoreContext, useWindows } from "./context.ts";
import { Dock } from "./Dock.tsx";
import { type DesktopActions, MenuBar } from "./MenuBar.tsx";
import { Widgets } from "./Widgets.tsx";
import { Window } from "./Window.tsx";
import { DOCK_RESERVE, MENUBAR_H, createWindowStore } from "./windowStore.ts";

function Windows({ actions }: { actions: DesktopActions & { focus: (app: AppId) => void } }) {
  const order = useWindows((s) => s.order);
  const windows = useWindows((s) => s.windows);
  const focused = useWindows((s) => s.focused);
  const setRect = useWindows((s) => s.setRect);
  // Rendered in a stable (alphabetical) DOM order so raising a window never remounts it.
  const ids = [...order].sort();
  return (
    <>
      {ids.map((id) => {
        const win = windows[id];
        if (!win) return null;
        return (
          <Window
            key={id}
            win={win}
            z={10 + order.indexOf(id)}
            focused={focused === id}
            onFocus={() => actions.focus(id)}
            onClose={() => actions.close(id)}
            onMinimize={() => actions.minimize(id)}
            onZoom={() => actions.zoom(id)}
            onRect={(rect) => setRect(id, rect, true)}
          />
        );
      })}
    </>
  );
}

export function Desktop() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const here = location.pathname + location.search;
  const [store] = useState(() => createWindowStore(here));

  useEffect(() => {
    store.getState().visit(here);
  }, [store, here, location.key]);

  const actions = useMemo(() => {
    const state = store.getState;
    const goTop = (except?: AppId) => void navigate(state().topmost(except)?.path ?? "/");
    return {
      focus: (app: AppId) => {
        const win = state().windows[app];
        if (win) void navigate(win.path);
      },
      open: (app: AppId) => void navigate(state().windows[app]?.path ?? APPS[app].defaultPath),
      close: (app: AppId) => {
        const wasFocused = state().focused === app;
        state().close(app);
        if (wasFocused) goTop();
      },
      minimize: (app: AppId) => {
        const wasFocused = state().focused === app;
        state().minimize(app);
        if (wasFocused) goTop(app);
      },
      zoom: (app: AppId) => state().toggleMaximize(app),
      closeAll: () => {
        state().order.forEach((app) => state().close(app));
        void navigate("/");
      },
      logout: () => {
        void api
          .logout()
          .catch(() => undefined)
          .then(() => {
            client.clear();
            void navigate("/login");
          });
      },
    };
  }, [store, navigate, client]);

  return (
    <WindowStoreContext.Provider value={store}>
      <div
        className="fixed inset-0 overflow-hidden text-fg"
        style={
          { "--os-top": `${MENUBAR_H}px`, "--os-bottom": `${DOCK_RESERVE}px` } as CSSProperties
        }
      >
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-10 focus:left-2 focus:z-[1100] focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-white"
        >
          {t("skipToContent")}
        </a>
        <div aria-hidden className="os-wallpaper absolute inset-0" />
        <Widgets />
        <main
          id="main"
          aria-label={t("os.desktop")}
          className="pointer-events-none absolute inset-0 *:pointer-events-auto"
        >
          <Windows actions={actions} />
        </main>
        <MenuBar actions={actions} />
        <Dock />
      </div>
    </WindowStoreContext.Provider>
  );
}
