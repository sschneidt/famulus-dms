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
    await user.type(screen.getByLabelText("Einrichtungscode"), "ABCD-EFGH-JKLM");
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
      setup_code: "ABCD-EFGH-JKLM",
      ocr_languages: ["deu", "eng"],
    });
    // Anmeldung als Weboberflaeche: Refresh-Token nur als HttpOnly-Cookie
    const loginCall = calls.find((c) => c.path === "/api/v1/auth/login");
    expect(loginCall).toBeDefined();
    expect(tokenStore.access).toBe("a");
  });

  it("Sprache vor der Anmeldung umschalten: Einrichtung auf Englisch, OCR-Sprachen passend vorgeschlagen", async () => {
    const { calls } = mockFetch([
      {
        path: "/api/v1/setup/status",
        body: {
          bootstrapped: false,
          ocr_languages: [
            { code: "deu", name: "Deutsch", installed: true },
            { code: "eng", name: "English", installed: true },
            { code: "rus", name: "Русский", installed: true },
            { code: "fra", name: "Français", installed: false },
          ],
        },
      },
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
      { method: "PATCH", path: "/api/v1/auth/me", body: { ...me, locale: "en" } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { path: "/login", routes });

    expect(await screen.findByText("Ersteinrichtung")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "English" }));
    expect(await screen.findByText("Initial setup")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    // Auswahl der OCR-Sprachen; Vorschlag = Oberflaechensprache + Deutsch (siehe Anfrage unten)
    expect(screen.getAllByLabelText("Languages of your documents").length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText("Setup code"), "ABCD-EFGH-JKLM");
    await user.type(screen.getByLabelText("Household name"), "The Smiths");
    await user.type(screen.getByLabelText("Your name"), "Anna");
    await user.type(screen.getByLabelText("Email"), "anna@example.com");
    await user.type(screen.getByLabelText("Password"), "geheim123");
    await user.type(screen.getByLabelText("Repeat password"), "geheim123");
    await user.click(screen.getByRole("button", { name: "Create household" }));

    expect(await screen.findByText("Startseite")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/setup/bootstrap")?.body).toMatchObject({
      default_language: "en",
      ocr_languages: ["eng", "deu"],
    });
    // die vor der Anmeldung gewaehlte Sprache wandert ins Konto
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/v1/auth/me")?.body).toEqual({ locale: "en" }),
    );
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

  it("fragt bei Zwei-Faktor-Konten nach dem Code aus der App", async () => {
    const { calls } = mockFetch([
      { path: "/api/v1/setup/status", body: { bootstrapped: true } },
      {
        method: "POST",
        path: "/api/v1/auth/login",
        body: { access_token: "", two_factor_required: true, challenge: "ch-1" },
      },
      { method: "POST", path: "/api/v1/auth/login/2fa", body: { access_token: "a2", notice: null } },
      { path: "/api/v1/auth/me", body: me },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { path: "/login", routes });

    await user.type(await screen.findByLabelText("E-Mail"), "anna@example.com");
    await user.type(screen.getByLabelText("Passwort"), "geheim123");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText("Bestätigungscode")).toBeInTheDocument();
    expect(tokenStore.access).toBeNull();

    await user.type(screen.getByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    expect(await screen.findByText("Startseite")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/auth/login/2fa")?.body).toEqual({ challenge: "ch-1", code: "123456" });
    expect(tokenStore.access).toBe("a2");
  });
});
