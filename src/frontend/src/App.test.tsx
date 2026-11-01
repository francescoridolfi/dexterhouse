// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App.tsx";

function stubFetch(impl: (input: RequestInfo | URL) => Promise<Response>) {
  const fetchMock = vi.fn(impl);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the title and a loading state, then the core status", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({ status: "ok" })));

    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "DexterHouse" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking core");
    expect(await screen.findByText("Core is up (ok)")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/health/live", expect.anything());
  });

  it("reports an HTTP error from the core", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: "down" }, 503)));

    render(<App />);

    expect(await screen.findByText(/Core unreachable: .*HTTP 503/)).toBeInTheDocument();
  });

  it("reports a network failure", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByText("Core unreachable: Failed to fetch")).toBeInTheDocument();
  });

  it("rejects an unexpected payload", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ alive: true })));

    render(<App />);

    expect(
      await screen.findByText("Core unreachable: Unexpected /health/live payload"),
    ).toBeInTheDocument();
  });
});
