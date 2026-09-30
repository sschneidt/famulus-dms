import { afterEach, describe, expect, it, vi } from "vitest";
import { createAuthFetch, onSessionExpired, tokenStore } from "./client";

const ORIGIN = "http://homedms.test";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Backend-Attrappe: akzeptiert nur das aktuell gueltige Access-Token, rotiert beim Refresh. */
function fakeBackend() {
  let valid = "access-2";
  let refreshCalls = 0;
  const base = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/auth/refresh") {
      refreshCalls += 1;
      const { refresh_token } = await request.json();
      if (refresh_token !== "refresh-1") return json(401, { detail: "Refresh-Token ungueltig" });
      await new Promise((r) => setTimeout(r, 5));
      valid = "access-3";
      return json(200, { access_token: "access-3", refresh_token: "refresh-2" });
    }
    if (request.headers.get("Authorization") !== `Bearer ${valid}`) return json(401, { detail: "abgelaufen" });
    const body = request.method === "POST" ? await request.text() : null;
    return json(200, { path, body });
  });
  return {
    base,
    get refreshCalls() {
      return refreshCalls;
    },
  };
}

afterEach(() => tokenStore.clear());

describe("authFetch", () => {
  it("haengt das Access-Token an", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-2", "refresh-1");
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/documents`);
    expect(resp.status).toBe(200);
    expect(backend.refreshCalls).toBe(0);
  });

  it("erneuert ein abgelaufenes Token und wiederholt die Anfrage inkl. Body", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1", "refresh-1");
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/wiedervorlagen/x/complete`, {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    });
    expect(resp.status).toBe(200);
    expect(await resp.json()).toEqual({ path: "/api/v1/wiedervorlagen/x/complete", body: '{"a":1}' });
    expect(tokenStore.access).toBe("access-3");
    expect(tokenStore.refresh).toBe("refresh-2");
  });

  it("teilt sich bei gleichzeitigen Anfragen EINE Erneuerung (rotierendes Refresh-Token)", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1", "refresh-1");
    const authFetch = createAuthFetch(backend.base);
    const responses = await Promise.all(["a", "b", "c"].map((p) => authFetch(`${ORIGIN}/api/v1/${p}`)));
    expect(responses.map((r) => r.status)).toEqual([200, 200, 200]);
    expect(backend.refreshCalls).toBe(1);
  });

  it("meldet abgelaufene Sitzung, wenn auch die Erneuerung scheitert", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1", "refresh-kaputt");
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/documents`);
    unsubscribe();
    expect(resp.status).toBe(401);
    expect(expired).toHaveBeenCalledOnce();
    expect(tokenStore.access).toBeNull();
    expect(tokenStore.refresh).toBeNull();
  });

  it("versucht ohne Refresh-Token keine Erneuerung (z. B. falsches Passwort beim Login)", async () => {
    const backend = fakeBackend();
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/auth/login`, { method: "POST", body: "{}" });
    expect(resp.status).toBe(401);
    expect(backend.refreshCalls).toBe(0);
  });
});
