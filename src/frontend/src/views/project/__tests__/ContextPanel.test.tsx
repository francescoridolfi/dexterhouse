// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useProjectStore } from "../../../store/projectStore.ts";
import { contextDoc, page, user } from "../../../test/e13Fixtures.ts";
import { event, snapshot } from "../../../test/fixtures.ts";
import { json, mockApi, renderWith } from "../../../test/render.tsx";
import { ContextPanel } from "../panels/ContextPanel.tsx";

const LIST = "GET /api/v1/projects/p-1/context";
const DOCS = [
  contextDoc(),
  contextDoc({ id: "doc-2", filename: "notes.md", status: "processing", uploaded_by: "x" }),
  contextDoc({ id: "doc-3", filename: "scan.pdf", status: "failed", error: "no_text_layer" }),
];

beforeEach(() => {
  useProjectStore.getState().snapshot(snapshot());
});
afterEach(() => {
  vi.unstubAllGlobals();
  useProjectStore.getState().reset(null);
});

describe("ContextPanel", () => {
  it("lists documents with size, status, failure reason and author", async () => {
    mockApi({ "GET /api/v1/auth/me": user("member"), [LIST]: page(DOCS) });
    renderWith(<ContextPanel />);
    const list = await screen.findByRole("list", { name: "Context documents" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("analysis.pdf");
    expect(rows[0]).toHaveTextContent("51 KB");
    expect(rows[0]).toHaveTextContent("processed");
    expect(rows[0]).toHaveTextContent("you,");
    expect(rows[1]).toHaveTextContent("processing");
    expect(rows[2]).toHaveTextContent("failed: scanned PDF without text (no OCR)");
    expect(within(rows[0]!).getByRole("link", { name: "Download analysis.pdf" })).toHaveAttribute(
      "href",
      "/api/v1/context/doc-1/download",
    );
    // Only the uploader (or an admin) may deactivate.
    expect(within(rows[0]!).getByRole("button", { name: /Deactivate/ })).toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button", { name: /Deactivate/ })).toBeNull();
  });

  it("previews the extracted text as plain text, never as HTML", async () => {
    mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: page(DOCS),
      "GET /api/v1/context/doc-1": contextDoc({
        content: "# Analysis\n<img src=x onerror=alert(1)> <b>bold</b>",
      }),
    });
    renderWith(<ContextPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Preview analysis.pdf" }));
    const text = await screen.findByLabelText("Extracted text");
    expect(text.tagName).toBe("PRE");
    expect(text).toHaveTextContent("<img src=x onerror=alert(1)> <b>bold</b>");
    expect(text.querySelector("img, b, h1")).toBeNull();
    expect(screen.getByText(/3 pages/)).toBeInTheDocument();
  });

  it("uploads files as multipart `file` and deactivates after confirmation", async () => {
    const { fetchMock, calls } = mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: page(DOCS),
      "POST /api/v1/projects/p-1/context": () =>
        json(contextDoc({ id: "doc-9", status: "processing" }), 202),
      "DELETE /api/v1/context/doc-1": () => json(null, 204),
    });
    renderWith(<ContextPanel />);
    const file = new File(["hello"], "brief.md", { type: "text/markdown" });
    await userEvent.upload(await screen.findByLabelText("Upload"), file);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBe(file);
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBeUndefined();

    await userEvent.click(screen.getByRole("button", { name: "Deactivate analysis.pdf" }));
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/v1/context/doc-1")).toBe(
        true,
      ),
    );
  });

  it("hides upload and deactivate from viewers", async () => {
    mockApi({ "GET /api/v1/auth/me": user("viewer"), [LIST]: page(DOCS) });
    renderWith(<ContextPanel />);
    await screen.findByText("analysis.pdf");
    expect(screen.queryByLabelText("Upload")).toBeNull();
    expect(screen.queryByRole("button", { name: /Deactivate/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Preview analysis.pdf" })).toBeInTheDocument();
  });

  it("refetches the list when a context event arrives", async () => {
    let processed = false;
    mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: () => json(page([contextDoc({ status: processed ? "processed" : "processing" })])),
    });
    renderWith(<ContextPanel />);
    expect(await screen.findByText("processing")).toBeInTheDocument();
    processed = true;
    act(() => {
      useProjectStore.getState().event(event("context.processed", { chars: 10 }));
    });
    expect(await screen.findByText("processed")).toBeInTheDocument();
  });
});
