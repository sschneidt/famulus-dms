import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";

export interface MockRoute {
  method?: string;
  path: string | RegExp;
  status?: number;
  body?: unknown;
}

/** fetch-Attrappe: beantwortet Anfragen anhand einer Liste; unbekannte -> 404. Protokolliert alle Aufrufe. */
export function mockFetch(routes: MockRoute[]) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    const text = await request.clone().text();
    let body: unknown = text;
    try {
      body = text ? JSON.parse(text) : undefined;
    } catch {
      /* kein JSON */
    }
    calls.push({ method: request.method, path: url.pathname + url.search, body });
    const route = routes.find(
      (r) =>
        (r.method ?? "GET") === request.method &&
        (typeof r.path === "string" ? r.path === url.pathname : r.path.test(url.pathname)),
    );
    if (!route) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    return new Response(route.body === undefined ? null : JSON.stringify(route.body), {
      status: route.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export function renderWithProviders(
  ui: ReactElement,
  { path = "/", routes }: { path?: string; routes?: RouteObject[] } = {},
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(routes ?? [{ path: "*", element: ui }], { initialEntries: [path] });
  return render(
    <MantineProvider>
      <DatesProvider settings={{ locale: "de" }}>
        <QueryClientProvider client={queryClient}>
          <ModalsProvider>
            <Notifications />
            <AuthProvider>
              <RouterProvider router={router} />
            </AuthProvider>
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>,
  );
}
