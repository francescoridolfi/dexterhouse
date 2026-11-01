// SPDX-License-Identifier: AGPL-3.0-or-later
// Frame-time check of the 3D office with 12 avatars (NFR-P3): a generated replay clip (12
// agents walking between rooms, working, using tools) is opened from the replay bar and
// played at 1×; the scene's own frame stats (`window.__dhOffice`) are read back.
// Numbers are printed; the assertion is loose because CI renders on SwiftShader (no GPU).
import { type Page, expect, test } from "@playwright/test";

/** Frame stats the scene keeps on `window.__dhOffice` (PerfMonitor). */
type Stats = { __dhOffice?: { frameMs: number[] } };

const USER = process.env.E2E_USER ?? "admin";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
const ROOMS = [
  "meeting_room",
  "design_studio",
  "open_space",
  "review_corner",
  "qa_lab",
  "pm_office",
];
const ROLES = ["analyst", "architect", "developer", "reviewer", "tester", "project_manager"];

function clip(projectId: string, agents = 12, seconds = 60) {
  const t0 = Date.parse("2026-11-01T10:00:00Z");
  let n = 0;
  const events: Record<string, unknown>[] = [];
  const add = (type: string, payload: Record<string, unknown>, atS: number) =>
    events.push({
      id: `bench-${String(++n).padStart(5, "0")}`,
      type,
      schema_version: 1,
      organization_id: "bench",
      project_id: projectId,
      actor: { type: "system", id: null, name: "system" },
      correlation_id: "bench",
      created_at: new Date(t0 + atS * 1000).toISOString(),
      payload,
    });
  add("project.created", { name: "Bench", budget: "50" }, 0);
  add("workspace.created", { workspace_id: "w" }, 0.5);
  for (let i = 0; i < agents; i++) {
    const id = `agent-${i}`;
    add(
      "agent.hired",
      {
        agent_id: id,
        role: ROLES[i % ROLES.length],
        display_name: `Agent ${i}`,
        room: "break_room",
      },
      1,
    );
    for (let s = 2 + (i % 4); s < seconds; s += 12) {
      const room = ROOMS[(i + s) % ROOMS.length];
      const turn = `${id}-t${s}`;
      add("agent.moved", { agent_id: id, from_room: "break_room", to_room: room }, s);
      add(
        "agent.turn.started",
        { agent_id: id, turn_id: turn, room, purpose: "benchmark" },
        s + 0.5,
      );
      for (let k = 1; k < 6; k++)
        add(
          "agent.tool.used",
          { turn_id: turn, tool: k % 2 ? "fs.read_file" : "fs.write_file" },
          s + k,
        );
      add(
        "agent.turn.completed",
        { agent_id: id, turn_id: turn, cost: "0.01", artifacts: [] },
        s + 6,
      );
      add("agent.moved", { agent_id: id, from_room: room, to_room: "break_room" }, s + 6.5);
    }
  }
  events.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  return {
    kind: "dexterhouse.replay-clip",
    schema: 1,
    project: { id: projectId, name: "Bench" },
    start_at: events[0].created_at,
    end_at: events.at(-1)!.created_at,
    exported_at: new Date().toISOString(),
    events,
  };
}

async function login(page: Page) {
  await page.goto("/login?lng=en");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
}

test("office frame time with 12 avatars", async ({ page }) => {
  test.skip(!PASSWORD, "E2E_PASSWORD is not set");
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const created = await page.request.post("/api/v1/projects", {
    headers: { "X-CSRFToken": csrf },
    data: {
      name: `Bench ${Date.now()}`,
      brief: "Frame-time benchmark of the office.",
      execution_mode: "supervised",
      budget: "1",
    },
  });
  expect(created.ok()).toBeTruthy();
  const { id } = (await created.json()) as { id: string };

  await page.goto(`/projects/${id}/office`);
  await expect(page.locator("[data-testid=office-canvas] canvas")).toBeVisible();
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "bench.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(clip(id))),
  });
  await expect(page.getByRole("slider", { name: "Replay position" })).toBeVisible();
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForTimeout(4_000);
  await page.evaluate(() => {
    const stats = (globalThis as unknown as Stats).__dhOffice;
    if (stats) stats.frameMs = [];
  });
  await page.waitForTimeout(10_000);
  const stats = await page.evaluate(() => {
    const ms = [...((globalThis as unknown as Stats).__dhOffice?.frameMs ?? [])].sort(
      (a, b) => a - b,
    );
    const pick = (q: number) => ms[Math.min(ms.length - 1, Math.floor(q * ms.length))] ?? NaN;
    return { frames: ms.length, p50: pick(0.5), p95: pick(0.95), fps: ms.length / 10 };
  });
  console.log(`[office-perf] 12 avatars: ${JSON.stringify(stats)}`);
  expect(stats.frames).toBeGreaterThan(20);
  expect(stats.p50).toBeLessThan(250);
});
