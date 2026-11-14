// SPDX-License-Identifier: AGPL-3.0-or-later
// Deep links of the Code and Graph apps: `/code/<project>?path=…&line=…&ref=…` and
// `/graph/<artifact>`. Every window (and the browser URL) can be opened from them.

export interface CodeTarget {
  path?: string | null;
  line?: number | null;
  ref?: string | null;
}

export function codeHref(projectId: string, target: CodeTarget = {}): string {
  const search = new URLSearchParams();
  if (target.path) search.set("path", target.path);
  if (target.line && target.line > 0) search.set("line", String(Math.floor(target.line)));
  if (target.ref && target.ref !== "HEAD") search.set("ref", target.ref);
  const text = search.toString();
  return `/code/${projectId}${text ? `?${text}` : ""}`;
}

/** `?path=…&line=…&ref=…` -> target; a bad line is dropped, a missing ref is HEAD. */
export function parseCodeSearch(search: string): Required<CodeTarget> & { ref: string } {
  const params = new URLSearchParams(search);
  const raw = Number(params.get("line"));
  return {
    path: params.get("path") || null,
    line: Number.isInteger(raw) && raw > 0 ? raw : null,
    ref: params.get("ref") || "HEAD",
  };
}

export function graphHref(artifactId: string): string {
  return `/graph/${artifactId}`;
}
