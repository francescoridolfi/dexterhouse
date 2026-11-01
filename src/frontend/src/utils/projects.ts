// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Project } from "../api/types.ts";

/** Open gates first, then the most recently updated (ux_2d_screens.md). */
export function sortProjects(projects: Project[]): Project[] {
  return [...projects].sort(
    (a, b) =>
      Number(b.open_gates_count > 0) - Number(a.open_gates_count > 0) ||
      b.updated_at.localeCompare(a.updated_at),
  );
}
