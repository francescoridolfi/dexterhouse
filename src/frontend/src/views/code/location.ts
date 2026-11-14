// SPDX-License-Identifier: AGPL-3.0-or-later
// Shell commands to get the code: clone the remote and check out the release branch, or
// copy the repository out of the workspace container when nothing was delivered.
import type { CodeLocation } from "../../api/types.ts";

export interface Command {
  id: "clone" | "checkout" | "copyOut";
  command: string;
}

/** POSIX single-quoting, so a URL or a branch name can never break the command. */
export function shellQuote(value: string): string {
  return /^[\w@%+=:,./-]+$/.test(value) ? value : `'${value.replace(/'/g, "'\\''")}'`;
}

export function repoDir(remote: string): string {
  const base = remote.replace(/\/+$/, "").split("/").pop() ?? "repo";
  return base.replace(/\.git$/, "") || "repo";
}

export function commands(data: CodeLocation): Command[] {
  const out: Command[] = [];
  const latest = data.releases[0];
  if (data.remote_url) {
    const dir = repoDir(data.remote_url);
    const clone = `git clone ${shellQuote(data.remote_url)}`;
    if (latest && latest.branch !== "main") {
      out.push({
        id: "checkout",
        command: `${clone} && cd ${shellQuote(dir)} && git checkout ${shellQuote(latest.branch)}`,
      });
    } else {
      out.push({ id: "clone", command: clone });
    }
  }
  if (data.workspace?.container_id) {
    out.push({
      id: "copyOut",
      command: `docker cp ${shellQuote(`${data.workspace.container_id}:${data.workspace.path}`)} ./workspace`,
    });
  }
  return out;
}
