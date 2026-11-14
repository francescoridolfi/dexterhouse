// SPDX-License-Identifier: AGPL-3.0-or-later
// Top menu bar: system menu, focused app name, Window menu; inbox, user and clock on the right.
import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useMe, useOpenGates } from "../api/queries.ts";
import { type Language, LANGUAGES, setLanguage } from "../i18n/index.ts";
import { useNow } from "../utils/useNow.ts";
import { APPS, type AppId } from "./apps.ts";
import { useWindows } from "./context.ts";
import { Menu, type MenuEntry } from "./Menu.tsx";
import { useWindowLabel } from "./titles.ts";

export interface DesktopActions {
  open: (app: AppId) => void;
  focus: (id: string) => void;
  close: (id: string) => void;
  minimize: (id: string) => void;
  zoom: (id: string) => void;
  closeAll: () => void;
  logout: () => void;
}

function Clock() {
  const { i18n } = useTranslation();
  const now = useNow(15_000);
  if (now === 0) return null;
  const date = new Date(now);
  const locale = i18n.language === "it" ? "it-IT" : "en-GB";
  return (
    <time dateTime={date.toISOString()} className="px-2 tabular-nums">
      <span className="max-sm:hidden">
        {date.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" })}
        &nbsp;&nbsp;
      </span>
      {date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
    </time>
  );
}

export function MenuBar({ actions }: { actions: DesktopActions }) {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const gates = useOpenGates();
  const inbox = gates.data?.results.length ?? 0;
  const focused = useWindows((s) => s.focused);
  const order = useWindows((s) => s.order);
  const windows = useWindows((s) => s.windows);
  const label = useWindowLabel();
  const focusedWin = focused ? windows[focused] : undefined;
  const language = i18n.language === "it" ? "it" : "en";

  const system: MenuEntry[] = [
    { heading: me.data?.organizations[0]?.name ?? "DexterHouse" },
    { label: t("nav.projects"), onSelect: () => actions.open("projects") },
    { label: t("projects.new"), onSelect: () => actions.open("newProject") },
    { label: `${t("nav.settings")}…`, onSelect: () => actions.open("settings") },
    "separator",
    { heading: t("language") },
    ...LANGUAGES.map((lng: Language) => ({
      label: lng === "it" ? "Italiano" : "English",
      checked: language === lng,
      onSelect: () => setLanguage(lng),
    })),
    "separator",
    {
      label: me.data?.display_name ? t("os.logoutAs", { name: me.data.display_name }) : t("logout"),
      onSelect: actions.logout,
    },
  ];

  const windowMenu: MenuEntry[] = [
    {
      label: t("os.window.minimize"),
      disabled: !focused,
      onSelect: () => focused && actions.minimize(focused),
    },
    {
      label: t("os.window.zoom"),
      disabled: !focused,
      onSelect: () => focused && actions.zoom(focused),
    },
    {
      label: t("os.window.close"),
      disabled: !focused,
      onSelect: () => focused && actions.close(focused),
    },
    { label: t("os.window.closeAll"), disabled: order.length === 0, onSelect: actions.closeAll },
    "separator",
    ...(order.length === 0
      ? [{ heading: t("os.window.none") }]
      : order.flatMap((id) => {
          const win = windows[id];
          return win
            ? [
                {
                  label: label(win),
                  checked: id === focused,
                  hint: win.minimized ? "—" : undefined,
                  onSelect: () => actions.focus(id),
                },
              ]
            : [];
        })),
  ];

  return (
    <header className="fixed inset-x-0 top-0 z-[1000] flex h-8 items-center gap-0.5 border-b border-white/5 bg-black/25 px-2 text-[13px] text-fg backdrop-blur-2xl backdrop-saturate-150">
      <Menu
        label={t("os.systemMenu")}
        entries={system}
        trigger={<img src="/favicon.svg" alt="" className="size-4" />}
      />
      <span className="px-2 font-semibold">
        {focusedWin ? t(APPS[focusedWin.app].title) : "DexterHouse"}
      </span>
      <Menu label={t("os.window.menu")} entries={windowMenu} trigger={t("os.window.menu")} />
      <div className="ml-auto flex items-center gap-0.5">
        <Link
          to="/inbox"
          aria-label={t("nav.inboxCount", { count: inbox })}
          className="relative flex h-6 items-center gap-1 rounded-md px-2 hover:bg-white/10"
        >
          <Bell aria-hidden className="size-3.5" />
          {inbox > 0 ? (
            <span className="rounded-full bg-[#ff453a] px-1.5 text-[10px] leading-4 font-bold text-white">
              {inbox}
            </span>
          ) : null}
        </Link>
        <span className="px-2 max-sm:hidden">{me.data?.display_name}</span>
        <Clock />
      </div>
    </header>
  );
}
