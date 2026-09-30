import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { mockFetch, renderWithProviders } from "../test/render";
import { me } from "../test/fixtures";
import { LoginPage } from "./LoginPage";

const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <div>Startseite</div> },
];

describe("LoginPage", () => {
  it("zeigt die Ersteinrichtung, solange kein Haushalt existiert, und meldet danach an", async () => {
    const { calls } = mockFetch([
      { path: "/api/v1/setup/status", body: { bootstrapped: false } },
      {
        method: "POST",
        path: "/api/v1/setup/bootstrap",
        status: 201,
        body: { tenant_id: "t1", admin_user_id: "u1", categories_created: 12 },
      },
      {
        method: "POST",
        path: "/api/v1/auth/login",
        body: { access_token: "a", refresh_token: "r", token_type: "bearer" },
      },
      { path: "/api/v1/auth/me", body: me },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { path: "/login", routes });

    expect(await screen.findByText("Ersteinrichtung")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name des Haushalts"), "Familie Muster");
    await user.type(screen.getByLabelText("Ihr Name"), "Anna");
    await user.type(screen.getByLabelText("E-Mail"), "anna@example.com");
    await user.type(screen.getByLabelText("Passwort"), "geheim123");
    await user.type(screen.getByLabelText("Passwort wiederholen"), "geheim124");
    await user.click(screen.getByRole("button", { name: "Haushalt anlegen" }));
    expect(await screen.findByText("Passwörter stimmen nicht überein")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/v1/setup/bootstrap")).toBe(false);

    await user.clear(screen.getByLabelText("Passwort wiederholen"));
    await user.type(screen.getByLabelText("Passwort wiederholen"), "geheim123");
    await user.click(screen.getByRole("button", { name: "Haushalt anlegen" }));

    expect(await screen.findByText("Startseite")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/setup/bootstrap")?.body).toEqual({
      household_name: "Familie Muster",
      default_language: "de",
      admin_display_name: "Anna",
      admin_email: "anna@example.com",
      admin_password: "geheim123",
    });
    expect(tokenStore.access).toBe("a");
  });

  it("zeigt die Fehlermeldung des Servers bei falschem Passwort", async () => {
    mockFetch([
      { path: "/api/v1/setup/status", body: { bootstrapped: true } },
      { method: "POST", path: "/api/v1/auth/login", status: 401, body: { detail: "E-Mail oder Passwort falsch" } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { path: "/login", routes });

    await user.type(await screen.findByLabelText("E-Mail"), "anna@example.com");
    await user.type(screen.getByLabelText("Passwort"), "falsch");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText("E-Mail oder Passwort falsch")).toBeInTheDocument();
    await waitFor(() => expect(tokenStore.access).toBeNull());
  });
});
