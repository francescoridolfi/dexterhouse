// SPDX-License-Identifier: AGPL-3.0-or-later
// The flat `ls-tree` listing as a folder tree, a name filter and the rows to render.
import type { CodeEntry } from "../../api/types.ts";

export interface TreeNode {
  name: string;
  path: string;
  dir: boolean;
  size: number | null;
  children: TreeNode[];
}

function sortNodes(nodes: TreeNode[]): void {
  nodes.sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name));
  nodes.forEach((n) => sortNodes(n.children));
}

export function buildTree(entries: CodeEntry[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", dir: true, size: null, children: [] };
  const dirs = new Map<string, TreeNode>([["", root]]);
  for (const entry of entries) {
    const parts = entry.path.split("/");
    let parent = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const path = parts.slice(0, i + 1).join("/");
      let dir = dirs.get(path);
      if (!dir) {
        dir = { name: parts[i]!, path, dir: true, size: null, children: [] };
        dirs.set(path, dir);
        parent.children.push(dir);
      }
      parent = dir;
    }
    parent.children.push({
      name: parts[parts.length - 1]!,
      path: entry.path,
      dir: false,
      size: entry.size,
      children: [],
    });
  }
  sortNodes(root.children);
  return root.children;
}

/** Files whose name (or path, when the query has a `/`) contains `query`, case-insensitive. */
export function matchFiles(entries: CodeEntry[], query: string, limit = 200): CodeEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const byPath = q.includes("/");
  const hits = entries.filter((e) => {
    const target = byPath ? e.path : (e.path.split("/").pop() ?? "");
    return target.toLowerCase().includes(q);
  });
  hits.sort((a, b) => a.path.length - b.path.length || a.path.localeCompare(b.path));
  return hits.slice(0, limit);
}

/** The folders to open so `path` is visible (`a/b/c.ts` -> `a`, `a/b`). */
export function ancestors(path: string): string[] {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join("/"));
}

export interface Row {
  node: TreeNode;
  depth: number;
}

/** Visible rows, depth-first, of the open folders. */
export function visibleRows(nodes: TreeNode[], open: Set<string>, depth = 0): Row[] {
  const rows: Row[] = [];
  for (const node of nodes) {
    rows.push({ node, depth });
    if (node.dir && open.has(node.path)) rows.push(...visibleRows(node.children, open, depth + 1));
  }
  return rows;
}

export function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
