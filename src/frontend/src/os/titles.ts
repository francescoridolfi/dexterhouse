// SPDX-License-Identifier: AGPL-3.0-or-later
// Window titles: the app name, the project name for a project window, and "Code — <project>"
// or "<graph name>" for the per-instance windows (names read from the query cache).
import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints.ts";
import { keys } from "../api/queries.ts";
import type { Artifact, Project } from "../api/types.ts";
import { useProjectStore } from "../store/projectStore.ts";
import { APPS } from "./apps.ts";
import type { Win } from "./windowStore.ts";

function instanceOf(win: Win): string | null {
  return win.id.includes(":") ? win.id.slice(win.id.indexOf(":") + 1) : null;
}

function titleFor(win: Win, t: TFunction, name: string | undefined): string {
  const app = t(APPS[win.app].title);
  if (!name) return app;
  if (win.app === "project" || win.app === "graph") return name;
  return `${app} — ${name}`;
}

function cachedName(client: QueryClient, win: Win): string | undefined {
  const id = instanceOf(win);
  if (!id) return undefined;
  if (win.app === "code") return client.getQueryData<Project>(keys.project(id))?.name;
  if (win.app === "graph") return client.getQueryData<Artifact>(keys.artifact(id))?.name;
  return undefined;
}

/** The title of a window (kept fresh: the project or artifact is fetched when needed). */
export function useWindowTitle(win: Win): string {
  const { t } = useTranslation();
  const projectName = useProjectStore((s) => s.project?.name);
  const id = instanceOf(win) ?? "";
  const project = useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.project(id),
    enabled: win.app === "code" && id !== "",
  });
  const artifact = useQuery({
    queryKey: keys.artifact(id),
    queryFn: () => api.artifact(id),
    enabled: win.app === "graph" && id !== "",
  });
  if (win.app === "project") return titleFor(win, t, projectName);
  return titleFor(win, t, project.data?.name ?? artifact.data?.name);
}

/** Labels for the Window menu, from the cache (the windows themselves fetch the names). */
export function useWindowLabel(): (win: Win) => string {
  const { t } = useTranslation();
  const client = useQueryClient();
  const projectName = useProjectStore((s) => s.project?.name);
  return (win) => titleFor(win, t, win.app === "project" ? projectName : cachedName(client, win));
}
