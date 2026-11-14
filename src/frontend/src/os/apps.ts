// SPDX-License-Identifier: AGPL-3.0-or-later
// DexterOS apps: every route belongs to one app, and each app has at most one window.
import {
  Bell,
  Briefcase,
  CodeXml,
  FolderKanban,
  type LucideIcon,
  Network,
  Package,
  Plus,
  Settings,
  TriangleAlert,
} from "lucide-react";

export type AppId =
  | "projects"
  | "newProject"
  | "project"
  | "code"
  | "graph"
  | "inbox"
  | "packages"
  | "settings"
  | "system";

export interface AppDef {
  id: AppId;
  /** i18n key of the app name (menu bar, window title, dock label). */
  title: string;
  icon: LucideIcon;
  /** Dock tile gradient (from → to). */
  tint: [string, string];
  defaultPath: string;
  size: { w: number; h: number };
  /** Closed when its window navigates to another app (a wizard, like "New project"). */
  transient?: boolean;
  /** Shown in the dock even when closed. */
  pinned?: boolean;
  /**
   * One window per instance (a project, an artifact) instead of one per app: the instance
   * read from the path. A path without one (a picker) gets a transient window.
   */
  instance?: (pathname: string) => string | null;
}

/** `/code/<id>/…` -> `<id>`. */
const secondSegment = (pathname: string) => pathname.split("/")[2] || null;

export const APPS: Record<AppId, AppDef> = {
  projects: {
    id: "projects",
    title: "nav.projects",
    icon: FolderKanban,
    tint: ["#5e9bff", "#2c4fe0"],
    defaultPath: "/projects",
    size: { w: 980, h: 640 },
    pinned: true,
  },
  newProject: {
    id: "newProject",
    title: "projects.new",
    icon: Plus,
    tint: ["#48d597", "#0f9c62"],
    defaultPath: "/projects/new",
    size: { w: 760, h: 720 },
    transient: true,
  },
  project: {
    id: "project",
    title: "os.app.project",
    icon: Briefcase,
    tint: ["#c08cff", "#7039e0"],
    defaultPath: "/projects",
    size: { w: 1240, h: 820 },
  },
  code: {
    id: "code",
    title: "os.app.code",
    icon: CodeXml,
    tint: ["#64d2ff", "#0a6cd6"],
    defaultPath: "/code",
    size: { w: 1180, h: 760 },
    pinned: true,
    instance: secondSegment,
  },
  graph: {
    id: "graph",
    title: "os.app.graph",
    icon: Network,
    tint: ["#5ee0c0", "#11806a"],
    defaultPath: "/projects",
    size: { w: 1120, h: 760 },
    instance: secondSegment,
  },
  inbox: {
    id: "inbox",
    title: "nav.inbox",
    icon: Bell,
    tint: ["#ffb340", "#f06a1d"],
    defaultPath: "/inbox",
    size: { w: 820, h: 620 },
    pinned: true,
  },
  packages: {
    id: "packages",
    title: "nav.packages",
    icon: Package,
    tint: ["#ff6f91", "#d1305c"],
    defaultPath: "/packages",
    size: { w: 1000, h: 660 },
    pinned: true,
  },
  settings: {
    id: "settings",
    title: "nav.settings",
    icon: Settings,
    tint: ["#a1a1aa", "#52525b"],
    defaultPath: "/settings",
    size: { w: 1000, h: 700 },
    pinned: true,
  },
  system: {
    id: "system",
    title: "os.app.system",
    icon: TriangleAlert,
    tint: ["#8e8e93", "#48484a"],
    defaultPath: "/",
    size: { w: 520, h: 360 },
  },
};

export const DOCK: AppId[] = ["projects", "code", "inbox", "packages", "settings"];

/** The app that owns a path; `null` is the bare desktop. */
export function appFor(path: string): AppId | null {
  const pathname = path.split(/[?#]/)[0]?.replace(/\/+$/, "") ?? "";
  if (pathname === "") return null;
  if (pathname === "/projects") return "projects";
  if (pathname === "/projects/new") return "newProject";
  if (pathname.startsWith("/projects/")) return "project";
  if (pathname === "/code" || pathname.startsWith("/code/")) return "code";
  if (pathname.startsWith("/graph/")) return "graph";
  if (pathname === "/inbox") return "inbox";
  if (pathname === "/packages" || pathname.startsWith("/packages/")) return "packages";
  if (pathname === "/settings" || pathname.startsWith("/settings/")) return "settings";
  return "system";
}

/** Key of the window that shows `path`: the app, or `app:instance`; `null` is the desktop. */
export function windowKey(path: string): string | null {
  const app = appFor(path);
  if (app === null) return null;
  const pathname = path.split(/[?#]/)[0]?.replace(/\/+$/, "") ?? "";
  const instance = APPS[app].instance?.(pathname);
  return instance ? `${app}:${instance}` : app;
}
