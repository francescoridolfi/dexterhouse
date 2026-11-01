// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { makeQueryClient } from "../utils/queryClient.ts";

export function renderWith(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

/** Route `fetch` by `METHOD path` (query string ignored unless the key includes it). */
type Handler = (body: unknown) => Response;

export function mockApi(routes: Record<string, Handler | object>) {
  const calls: { method: string; path: string; body: unknown; headers: Record<string, string> }[] =
    [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(
      input instanceof Request ? input.url : input.toString(),
      "http://localhost",
    );
    const method = init?.method ?? "GET";
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({
      method,
      path: url.pathname + url.search,
      body,
      headers: (init?.headers ?? {}) as Record<string, string>,
    });
    const route =
      routes[`${method} ${url.pathname}${url.search}`] ?? routes[`${method} ${url.pathname}`];
    if (route === undefined) return Promise.resolve(json({ title: "Not found", status: 404 }, 404));
    return Promise.resolve(
      typeof route === "function" ? (route as (b: unknown) => Response)(body) : json(route),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}
