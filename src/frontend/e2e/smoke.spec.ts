// SPDX-License-Identifier: AGPL-3.0-or-later
// Smoke (testing.md): projects list → project page → gate decisions, against the real core
// with the built-in agents on the gateway's `fake` provider (the stack must run with
// GATEWAY_FAKE_RESPONDER=dexterhouse.apps.agents.demo.respond): no real LLM is called.
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

/** What an admin does in Settings → Model profiles: every chat profile on `fake`. */
async function useFakeProvider(page: Page) {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrftoken")?.value ?? "";
  for (const profile of ["strong", "balanced", "fast"]) {
    const response = await page.request.put(`/api/v1/model-profiles/${profile}`, {
      headers: { "X-CSRFToken": csrf },
      data: { provider: "fake", model: "fake-model", is_local: true },
    });
    expect(response.ok()).toBeTruthy();
  }
}

test("create a project, follow it live and decide its gates", async ({ page }) => {
  test.skip(!PASSWORD, "E2E_PASSWORD is not set");
  test.setTimeout(240_000);
  const name = `Smoke ${Date.now()}`;
  await login(page);
  await useFakeProvider(page);

  await page.getByRole("link", { name: "New project" }).first().click();
  await page.getByLabel("Name").fill(name);
  await page
    .getByLabel("Brief (Markdown)")
    .fill("A web app for a small gym: courses and bookings.");
  await expect(page.getByText(/Similar projects:/)).toBeVisible();
  await page.getByRole("button", { name: "Start", exact: true }).click();

  // Project page: mode badge and budget always visible, live connection.
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByRole("button", { name: /SUPERVISED mode/ })).toBeVisible();
  await expect(page.getByRole("meter", { name: "Budget used" })).toBeVisible();
  await expect(page.getByText("live", { exact: true })).toBeVisible();

  // Back to the list: the project is there; open it again from the list.
  await expect(page.getByText(/Open gate/i)).toBeVisible({ timeout: 90_000 });
  await page.getByRole("link", { name: "Projects" }).first().click();
  const row = page.getByRole("link", { name: new RegExp(name) });
  await expect(row).toBeVisible();
  await row.click();

  // First gate: the analyst's questions.
  await page.getByRole("button", { name: "Open panel" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByText("Questions", { exact: true })).toBeVisible();
  for (const group of await panel.getByRole("radiogroup").all()) {
    await group.getByRole("radio").first().check();
  }
  for (const assume of await panel.getByRole("button", { name: "Use the assumption" }).all()) {
    await assume.click();
  }
  await panel.getByRole("button", { name: "Send answers" }).click();
  await expect(panel.getByText(/the agent resumes/)).toBeVisible();
  await panel.getByRole("button", { name: "Close" }).click();

  // Next gate: approval of the analysis, decided from the panel.
  await expect(page.getByText(/Approval — /)).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "Open panel" }).click();
  await expect(page.getByRole("dialog").getByRole("tab").first()).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/moves to the next phase/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

  // The decision is in the live log, and the turns were paid on the fake provider.
  await expect(page.getByText(/gate decided: approve by/).first()).toBeVisible();
  await page.getByRole("tab", { name: "Costs" }).click();
  await expect(page.getByText("fake/fake-model").first()).toBeVisible();
  await page.getByRole("tab", { name: "Log" }).click();
  await expect(page.getByText("Event timeline")).toBeVisible();

  // The 3D office: lazy chunk, canvas mounted, the team in the scene, replay from events.
  await page.getByRole("tab", { name: "Office 3D" }).click();
  await expect(page.locator("[data-testid=office-canvas] canvas")).toBeVisible();
  await expect(page.getByRole("img", { name: /\d+ agents/ })).toBeVisible();
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  await expect(page.getByRole("slider", { name: "Replay position" })).toBeVisible();
  await page.getByRole("button", { name: "Next gate" }).click();
  await page.getByRole("button", { name: "Back to live" }).click();
});
