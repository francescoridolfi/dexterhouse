// SPDX-License-Identifier: AGPL-3.0-or-later
// Smoke (testing.md): projects list → project page → gate decisions, against the real core.
// The stack runs the default turn runner, so no real LLM provider is called.
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

test("create a project, follow it live and decide its gates", async ({ page }) => {
  test.skip(!PASSWORD, "E2E_PASSWORD is not set");
  const name = `Smoke ${Date.now()}`;
  await login(page);

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

  // Back to the list: the project is there, with its open gate.
  await expect(page.getByText(/Open gate/i)).toBeVisible({ timeout: 60_000 });
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
  await panel.getByRole("button", { name: "Send answers" }).click();
  await expect(panel.getByText(/the agent resumes/)).toBeVisible();
  await panel.getByRole("button", { name: "Close" }).click();

  // Next gate: approval of the analysis, decided from the panel.
  await expect(page.getByText(/Approval — /)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Open panel" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/moves to the next phase/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

  // The pipeline moved on and the decision is in the live log.
  await expect(page.getByText(/gate decided: approve by/).first()).toBeVisible();
  await page.getByRole("tab", { name: "Log" }).click();
  await expect(page.getByRole("heading", { name: "Event timeline" })).toBeVisible();
});
