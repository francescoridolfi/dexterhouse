// SPDX-License-Identifier: AGPL-3.0-or-later
// E-13 (docs/specs/change-requests.md): a completed project reopens with a change request.
// Same stack as smoke.spec.ts (fake provider); the brief iteration runs in autonomous mode
// through the API, the change request is written and started from the Changes tab.
import { type Page, expect, test } from "@playwright/test";

const USER = process.env.E2E_USER ?? "admin";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

async function login(page: Page) {
  await page.goto("/login?lng=en");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
}

async function csrf(page: Page): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  return { "X-CSRFToken": cookies.find((c) => c.name === "csrftoken")?.value ?? "" };
}

async function completedProject(page: Page, name: string): Promise<string> {
  const headers = await csrf(page);
  for (const profile of ["strong", "balanced", "fast"]) {
    const response = await page.request.put(`/api/v1/model-profiles/${profile}`, {
      headers,
      data: { provider: "fake", model: "fake-model", is_local: true },
    });
    expect(response.ok()).toBeTruthy();
  }
  const created = await page.request.post("/api/v1/projects", {
    headers,
    data: {
      name,
      brief: "A web app for a small gym: courses and bookings.",
      budget: 10,
      execution_mode: "autonomous",
    },
  });
  expect(created.ok()).toBeTruthy();
  const { id } = (await created.json()) as { id: string };
  expect((await page.request.post(`/api/v1/projects/${id}/start`, { headers })).ok()).toBeTruthy();
  await expect
    .poll(
      async () =>
        ((await (await page.request.get(`/api/v1/projects/${id}`)).json()) as { status: string })
          .status,
      { timeout: 180_000, intervals: [2_000] },
    )
    .toBe("completed");
  return id;
}

test("a completed project reopens with a change request", async ({ page }) => {
  test.skip(!PASSWORD, "E2E_PASSWORD is not set");
  test.setTimeout(300_000);
  await login(page);
  const id = await completedProject(page, `CR ${Date.now()}`);

  await page.goto(`/projects/${id}/changes`);
  const win = page.locator("section[data-focused]");
  await win.getByRole("button", { name: "New change request" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("Title").fill("Waiting list");
  await form
    .getByPlaceholder(/Describe the change/)
    .fill("Add a waiting list to full slots (FIFO).");
  await form.getByRole("button", { name: "Create draft" }).click();

  const row = win.getByRole("button", { name: /CR-1.*Waiting list/ });
  await expect(row).toBeVisible();
  await row.click();
  await win.getByRole("button", { name: "Start", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Start" }).click();

  // The project reopens: the header shows the CR being worked on.
  await expect(win.getByText("CR-1 · running")).toBeVisible({ timeout: 30_000 });
});
