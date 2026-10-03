import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { routes } from "../routes";
import { categories, me, page } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";

describe("Profil & Haushalt", () => {
  it("Name 'string' aus der Einrichtung laesst sich im Benutzermenue korrigieren", async () => {
    tokenStore.set("a", "r");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: { ...me, display_name: "string", household_name: "string" } },
      { method: "PATCH", path: "/api/v1/auth/me", body: { ...me, display_name: "Silvester" } },
      { method: "PATCH", path: "/api/v1/tenant", body: { name: "Familie S", documents_refiled: 3 } },
      { path: "/api/v1/categories", body: categories },
      { path: "/api/v1/documents", body: page([]) },
      { path: "/api/v1/documents/needs-review", body: page([]) },
      { path: "/api/v1/wiedervorlagen", body: page([]) },
      { path: "/api/v1/documents/unpaid", body: { items: [], total: 0, total_amount: 0 } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<></>, { routes });

    await user.click(await screen.findByRole("button", { name: "Benutzermenü" }));
    await user.click(await screen.findByRole("menuitem", { name: "Profil & Haushalt" }));
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
    // danach werden die Nutzerangaben neu geladen
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/api/v1/auth/me" && c.method === "GET")).toHaveLength(2),
    );
  });

  it("eigenes Passwort ändern meldet sich danach mit dem neuen Passwort neu an", async () => {
    tokenStore.set("a", "r");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { method: "PUT", path: "/api/v1/auth/password", status: 204 },
      { method: "POST", path: "/api/v1/auth/login", body: { access_token: "neu", refresh_token: "neu-r" } },
      { path: "/api/v1/categories", body: categories },
      { path: "/api/v1/documents", body: page([]) },
      { path: "/api/v1/documents/needs-review", body: page([]) },
      { path: "/api/v1/wiedervorlagen", body: page([]) },
      { path: "/api/v1/documents/unpaid", body: { items: [], total: 0, total_amount: 0 } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<></>, { routes });

    await user.click(await screen.findByRole("button", { name: "Benutzermenü" }));
    await user.click(await screen.findByRole("menuitem", { name: "Profil & Haushalt" }));
    await user.click(await screen.findByRole("button", { name: "Passwort ändern" }));
    await user.type(screen.getByLabelText("Bisheriges Passwort"), "alt-passwort");
    await user.type(screen.getByLabelText("Neues Passwort"), "neues-passwort");
    await user.type(screen.getByLabelText("Neues Passwort wiederholen"), "neues-passwort");
    const buttons = screen.getAllByRole("button", { name: "Passwort ändern" });
    await user.click(buttons[buttons.length - 1]);

    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/v1/auth/login")?.body).toEqual({
        email: me.email,
        password: "neues-passwort",
      }),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      current_password: "alt-passwort",
      new_password: "neues-passwort",
    });
    expect(tokenStore.access).toBe("neu");
  });
});
