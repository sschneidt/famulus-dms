import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { routes } from "../routes";
import { categories, me, page } from "../test/fixtures";
import { mockFetch, renderWithProviders, type MockRoute } from "../test/render";

const BASIS: MockRoute[] = [
  { path: "/api/v1/categories", body: categories },
  { path: "/api/v1/documents", body: page([]) },
  { path: "/api/v1/documents/needs-review", body: page([]) },
  { path: "/api/v1/documents/unanalyzed", body: { items: [], total: 0, ai_available: true } },
  { path: "/api/v1/wiedervorlagen", body: page([]) },
  { path: "/api/v1/documents/unpaid", body: { items: [], total: 0, total_amount: 0 } },
  { path: "/api/v1/setup/status", body: { bootstrapped: true, tls: true, http_port: 8000, https_port: 8443 } },
  { path: "/api/v1/auth/2fa", body: { enabled: false, recovery_codes_left: 0 } },
  {
    path: "/api/v1/auth/sessions",
    body: [
      {
        id: "s1",
        device: "Chrome auf Windows",
        ip: "192.168.1.20",
        current: true,
        last_used_at: "2026-10-03T10:00:00Z",
      },
      {
        id: "s2",
        device: "Safari auf iPhone",
        ip: "192.168.1.31",
        current: false,
        last_used_at: "2026-10-02T18:00:00Z",
      },
    ],
  },
];

function render(routesExtra: MockRoute[], meOverride: object = {}) {
  tokenStore.set("a");
  const result = mockFetch([{ path: "/api/v1/auth/me", body: { ...me, ...meOverride } }, ...routesExtra, ...BASIS]);
  renderWithProviders(<></>, { routes, path: "/konto" });
  return result;
}

describe("Konto & Sicherheit", () => {
  it("Name 'string' aus der Einrichtung laesst sich korrigieren (über das Benutzermenü erreichbar)", async () => {
    const { calls } = render(
      [
        { method: "PATCH", path: "/api/v1/auth/me", body: { ...me, display_name: "Silvester" } },
        { method: "PATCH", path: "/api/v1/tenant", body: { name: "Familie S", documents_refiled: 3 } },
      ],
      { display_name: "string", household_name: "string" },
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Benutzermenü" }));
    expect(await screen.findByRole("menuitem", { name: "Konto & Sicherheit" })).toHaveAttribute("href", "/konto");
    await user.keyboard("{Escape}");

    const name = await screen.findByLabelText("Dein Name");
    await user.clear(name);
    await user.type(name, "Silvester");
    const household = screen.getByLabelText(/Name des Haushalts/);
    await user.clear(household);
    await user.type(household, "Familie S");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => {
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/v1/auth/me")?.body).toEqual({
        display_name: "Silvester",
      });
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/v1/tenant")?.body).toEqual({
        name: "Familie S",
      });
    });
  });

  it("Passwort ändern - dieses Gerät bleibt angemeldet", async () => {
    const { calls } = render([{ method: "PUT", path: "/api/v1/auth/password", status: 204 }]);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Bisheriges Passwort"), "alt-passwort");
    await user.type(screen.getByLabelText("Neues Passwort"), "neues-passwort");
    await user.type(screen.getByLabelText("Neues Passwort wiederholen"), "neues-passwort");
    await user.click(screen.getByRole("button", { name: "Passwort ändern" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        current_password: "alt-passwort",
        new_password: "neues-passwort",
      }),
    );
    expect(calls.some((c) => c.path === "/api/v1/auth/login")).toBe(false);
    expect(tokenStore.access).toBe("a");
  });

  it("Zwei-Faktor einrichten: Passwort, QR-Code, Code, Wiederherstellungscodes", async () => {
    const { calls } = render([
      {
        method: "POST",
        path: "/api/v1/auth/2fa/setup",
        body: { secret: "JBSWY3DPEHPK3PXP", uri: "otpauth://totp/x", qr_svg: '<svg data-testid="qr-svg"></svg>' },
      },
      { method: "POST", path: "/api/v1/auth/2fa/enable", body: { recovery_codes: ["abcd-efgh", "jkmn-pqrs"] } },
    ]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Einrichten" }));
    await user.type(await screen.findByLabelText("Zur Sicherheit: dein Passwort"), "mein-passwort");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByTestId("qr-svg")).toBeInTheDocument();
    expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/6-stelligen Code/), "123456");
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    const codes = await screen.findByTestId("recovery-codes");
    expect(within(codes).getByText("abcd-efgh")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/auth/2fa/setup")?.body).toEqual({ password: "mein-passwort" });
    expect(calls.find((c) => c.path === "/api/v1/auth/2fa/enable")?.body).toEqual({ code: "123456" });
  });

  it("listet angemeldete Geräte und meldet ein fremdes ab; zeigt den Weg für neue Geräte", async () => {
    const { calls } = render([{ method: "DELETE", path: "/api/v1/auth/sessions/s2", status: 204 }]);
    const user = userEvent.setup();
    const rows = await screen.findAllByTestId("session");
    expect(within(rows[0]).getByText("dieses Gerät")).toBeInTheDocument();
    expect(within(rows[0]).queryByRole("button")).toBeNull();
    await user.click(within(rows[1]).getByRole("button", { name: "Safari auf iPhone abmelden" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/v1/auth/sessions/s2")).toBe(true),
    );
    expect(screen.getByRole("link", { name: /\/zertifikat$/ })).toHaveAttribute(
      "href",
      "http://localhost:8000/zertifikat",
    );
  });

  it("Sprache umschalten: wird im Konto gespeichert und gilt sofort", async () => {
    let locale = "de";
    tokenStore.set("a");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: () => ({ ...me, locale }) },
      { method: "PATCH", path: "/api/v1/auth/me", body: () => ((locale = "ru"), { ...me, locale }) },
      ...BASIS,
    ]);
    renderWithProviders(<></>, { routes, path: "/konto" });
    const user = userEvent.setup();
    const select = await screen.findByRole("combobox", { name: "Sprache" });
    calls.length = 0;
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "Русский", hidden: true }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/v1/auth/me")?.body).toEqual({ locale: "ru" }),
    );
    expect(await screen.findByText("Двухфакторный вход")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("ru");
  });
});
