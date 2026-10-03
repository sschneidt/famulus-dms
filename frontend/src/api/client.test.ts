import { afterEach, describe, expect, it, vi } from "vitest";
import { createAuthFetch, onSessionExpired, tokenStore } from "./client";

const ORIGIN = "http://homedms.test";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Backend-Attrappe: akzeptiert nur das aktuell gueltige Access-Token. Die Erneuerung laeuft ueber
 * das HttpOnly-Cookie - der Client schickt dafuer nur die Kennung "X-HomeDMS-Session: cookie".
 */
function fakeBackend({ sessionValid = true } = {}) {
  let valid = "access-2";
  let refreshCalls = 0;
  const base = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/auth/refresh") {
      refreshCalls += 1;
      expect(request.headers.get("X-HomeDMS-Session")).toBe("cookie");
      expect(init?.credentials ?? request.credentials).toBe("same-origin");
      if (!sessionValid) return json(401, { detail: "Anmeldung abgelaufen" });
      await new Promise((r) => setTimeout(r, 5));
      valid = "access-3";
      return json(200, { access_token: "access-3", refresh_token: null });
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
    tokenStore.set("access-2");
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/documents`);
    expect(resp.status).toBe(200);
    expect(backend.refreshCalls).toBe(0);
  });

  it("Tokens liegen nie im Browser-Speicher - dort steht nur, dass es eine Anmeldung gibt", () => {
    tokenStore.set("geheim");
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("geheim");
    expect(tokenStore.hasSession).toBe(true);
  });

  it("erneuert ein abgelaufenes Token per Cookie und wiederholt die Anfrage inkl. Body", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1");
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/wiedervorlagen/x/complete`, {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    });
    expect(resp.status).toBe(200);
    expect(await resp.json()).toEqual({ path: "/api/v1/wiedervorlagen/x/complete", body: '{"a":1}' });
    expect(tokenStore.access).toBe("access-3");
  });

  it("nach dem Neuladen (kein Token im Speicher) erst per Cookie fortsetzen", async () => {
    const backend = fakeBackend();
    tokenStore.set("x");
    tokenStore.clear();
    window.localStorage.setItem("homedms.session", "1"); // Seite neu geladen: nur das Kennzeichen ist noch da
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/documents`);
    expect(resp.status).toBe(200);
    expect(backend.refreshCalls).toBe(1);
  });

  it("teilt sich bei gleichzeitigen Anfragen EINE Erneuerung (rotierendes Refresh-Token)", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1");
    const authFetch = createAuthFetch(backend.base);
    const responses = await Promise.all(["a", "b", "c"].map((p) => authFetch(`${ORIGIN}/api/v1/${p}`)));
    expect(responses.map((r) => r.status)).toEqual([200, 200, 200]);
    expect(backend.refreshCalls).toBe(1);
  });

  it("meldet abgelaufene Sitzung, wenn auch die Erneuerung scheitert", async () => {
    const backend = fakeBackend({ sessionValid: false });
    tokenStore.set("access-1");
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/documents`);
    unsubscribe();
    expect(resp.status).toBe(401);
    expect(expired).toHaveBeenCalledOnce();
    expect(tokenStore.access).toBeNull();
    expect(tokenStore.hasSession).toBe(false);
  });

  it("versucht beim Anmelden keine Erneuerung (z. B. falsches Passwort)", async () => {
    const backend = fakeBackend();
    tokenStore.set("access-1");
    const resp = await createAuthFetch(backend.base)(`${ORIGIN}/api/v1/auth/login`, { method: "POST", body: "{}" });
    expect(resp.status).toBe(401);
    expect(backend.refreshCalls).toBe(0);
  });

  it("raeumt alte Tokens aus dem Browser-Speicher frueherer Versionen weg", async () => {
    window.localStorage.setItem("homedms.refreshToken", "alt");
    vi.resetModules();
    await import("./client");
    expect(window.localStorage.getItem("homedms.refreshToken")).toBeNull();
  });
});
