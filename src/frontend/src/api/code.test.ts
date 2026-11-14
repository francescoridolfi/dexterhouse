// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from "vitest";

import { codeFile, codeLocation, codeTree } from "../test/codeFixtures.ts";
import { json, mockApi } from "../test/render.tsx";
import { ApiError } from "./client.ts";
import { api } from "./endpoints.ts";

afterEach(() => vi.unstubAllGlobals());

describe("code API client", () => {
  it("calls the read-only code endpoints with their query", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p-1/code/tree": codeTree,
      "GET /api/v1/projects/p-1/code/file": codeFile("src/a.py"),
      "GET /api/v1/projects/p-1/code/log": { ref: "HEAD", branch: "main", commits: [] },
      "GET /api/v1/projects/p-1/code/location": codeLocation,
    });
    expect((await api.codeTree("p-1")).commit).toBe(codeTree.commit);
    await api.codeTree("p-1", "abc");
    expect((await api.codeFile("p-1", "src/a b.py", "HEAD")).path).toBe("src/a.py");
    await api.codeLog("p-1", undefined, 10);
    expect((await api.codeLocation("p-1")).releases).toHaveLength(1);
    expect(calls.map((c) => c.path)).toEqual([
      "/api/v1/projects/p-1/code/tree",
      "/api/v1/projects/p-1/code/tree?ref=abc",
      "/api/v1/projects/p-1/code/file?path=src%2Fa+b.py&ref=HEAD",
      "/api/v1/projects/p-1/code/log?limit=10",
      "/api/v1/projects/p-1/code/location",
    ]);
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("surfaces the problem of an unavailable workspace", async () => {
    mockApi({
      "GET /api/v1/projects/p-1/code/tree": () =>
        json({ title: "Workspace unavailable", status: 503, detail: "no live workspace" }, 503),
    });
    const error = await api.codeTree("p-1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toBe("no live workspace");
  });
});
