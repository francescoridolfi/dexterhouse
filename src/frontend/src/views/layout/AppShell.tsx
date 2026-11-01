// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQueryClient } from "@tanstack/react-query";
import { Bell, FolderKanban, LogOut, Menu, Moon, Package, Settings, Sun } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../../api/endpoints.ts";
import { useMe, useOpenGates } from "../../api/queries.ts";
import { type Language, LANGUAGES, setLanguage } from "../../i18n/index.ts";
import { setTheme, useDarkMode } from "../../utils/theme.ts";

const NAV = [
  { to: "/projects", icon: FolderKanban, key: "nav.projects" },
  { to: "/inbox", icon: Bell, key: "nav.inbox" },
  { to: "/packages", icon: Package, key: "nav.packages" },
  { to: "/settings", icon: Settings, key: "nav.settings" },
] as const;

/** Global header + collapsible sidebar (ux_2d_screens.md). */
export function AppShell() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const dark = useDarkMode();
  const me = useMe();
  const gates = useOpenGates();
  const client = useQueryClient();
  const navigate = useNavigate();
  const inbox = gates.data?.results.length ?? 0;

  const logout = async () => {
    await api.logout().catch(() => undefined);
    client.clear();
    void navigate("/login");
  };

  return (
    <div className="flex min-h-screen bg-bg text-fg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-2"
      >
        {t("skipToContent")}
      </a>
      <nav
        aria-label={t("nav.label")}
        className={`${open ? "flex" : "hidden"} fixed inset-y-0 left-0 z-30 w-60 flex-col border-r border-line bg-surface p-3 md:static md:flex md:w-16 xl:w-60`}
      >
        <div className="mb-4 flex h-11 items-center gap-2 px-2 font-semibold">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="md:hidden xl:inline">DexterHouse</span>
        </div>
        {NAV.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `flex min-h-11 items-center gap-3 rounded-card px-3 text-sm ${isActive ? "bg-bg font-semibold text-accent" : "text-muted hover:text-fg"}`
            }
          >
            <Icon aria-hidden className="size-5 shrink-0" />
            <span className="md:sr-only xl:not-sr-only">{t(key)}</span>
            {to === "/inbox" && inbox > 0 ? (
              <span className="ml-auto rounded-full bg-blocked px-1.5 text-xs font-bold text-black md:hidden xl:inline">
                {inbox}
              </span>
            ) : null}
          </NavLink>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-surface px-4">
          <button
            type="button"
            className="grid size-11 place-items-center rounded-card md:hidden"
            aria-label={t("nav.toggle")}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Menu aria-hidden className="size-5" />
          </button>
          <span className="truncate text-sm text-muted">{me.data?.organizations[0]?.name}</span>
          <div className="ml-auto flex items-center gap-1">
            <NavLink
              to="/inbox"
              className="relative grid size-11 place-items-center rounded-card hover:bg-bg"
              aria-label={t("nav.inboxCount", { count: inbox })}
            >
              <Bell aria-hidden className="size-5" />
              {inbox > 0 ? (
                <span className="absolute top-1.5 right-1.5 grid min-w-4 place-items-center rounded-full bg-blocked px-1 text-[10px] font-bold text-black">
                  {inbox}
                </span>
              ) : null}
            </NavLink>
            <label className="sr-only" htmlFor="language">
              {t("language")}
            </label>
            <select
              id="language"
              value={i18n.language === "it" ? "it" : "en"}
              onChange={(e) => setLanguage(e.target.value as Language)}
              className="min-h-11 rounded-card bg-transparent px-2 text-sm"
            >
              {LANGUAGES.map((lng) => (
                <option key={lng} value={lng}>
                  {lng.toUpperCase()}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setTheme(dark ? "light" : "dark")}
              aria-label={dark ? t("theme.light") : t("theme.dark")}
              className="grid size-11 place-items-center rounded-card hover:bg-bg"
            >
              {dark ? (
                <Sun aria-hidden className="size-5" />
              ) : (
                <Moon aria-hidden className="size-5" />
              )}
            </button>
            <span className="hidden px-2 text-sm sm:inline">{me.data?.display_name}</span>
            <button
              type="button"
              onClick={() => void logout()}
              aria-label={t("logout")}
              className="grid size-11 place-items-center rounded-card hover:bg-bg"
            >
              <LogOut aria-hidden className="size-5" />
            </button>
          </div>
        </header>
        <main id="main" className="min-w-0 flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
