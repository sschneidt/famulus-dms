import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../api/client";
import { me } from "../test/fixtures";
import { mockFetch, renderWithProviders, type MockRoute } from "../test/render";
import { MailSettingsCard } from "./MailSettingsCard";
import { NotificationBell } from "./NotificationBell";
import { NotificationSettingsSection } from "./NotificationSettingsSection";

const settings = (over: object = {}) => ({
  email: true,
  push: false,
  digest_hour: 7,
  email_address: "admin@example.com",
  email_available: true,
  push_public_key: "BElzZ2V0ZXN0",
  push_devices: [],
  timezone: "Europe/Berlin",
  ...over,
});

function render(
  ui: React.ReactElement,
  routes: MockRoute[],
  extraRoutes: { path: string; element: React.ReactElement }[] = [],
) {
  tokenStore.set("a");
  const result = mockFetch([{ path: "/api/v1/auth/me", body: me }, ...routes]);
  renderWithProviders(<></>, { routes: [{ path: "/", element: ui }, ...extraRoutes] });
  return result;
}

afterEach(() => vi.unstubAllGlobals());

describe("Glocke (Benachrichtigungscenter)", () => {
  it("zeigt ungelesene Erinnerungen und öffnet das Dokument", async () => {
    const { calls } = render(
      <NotificationBell />,
      [
        {
          path: "/api/v1/notifications",
          body: {
            unread: 1,
            items: [
              {
                id: "n1",
                type: "wiedervorlage_due",
                title: "Kündigungsfrist",
                body: "Kfz-Versicherung: in 7 Tagen fällig (So, 11.10.2026)",
                url: "/dokumente/d1",
                read: false,
                created_at: "2026-10-04T05:00:00Z",
              },
              {
                id: "n2",
                type: "needs_review",
                title: "Kategorie prüfen",
                body: "2 neue Dokumente warten auf eine Einordnung.",
                url: "/pruefen",
                read: true,
                created_at: "2026-10-03T05:00:00Z",
              },
            ],
          },
        },
        { method: "POST", path: "/api/v1/notifications/n1/read", status: 204 },
        { method: "POST", path: "/api/v1/notifications/read-all", status: 204 },
      ],
      [{ path: "/dokumente/:id", element: <div>Dokumentseite</div> }],
    );
    const user = userEvent.setup();
    const bell = await screen.findByRole("button", { name: "Benachrichtigungen (1 ungelesen)" });
    await user.click(bell);
    const items = await screen.findAllByTestId("notification");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText(/in 7 Tagen fällig/)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Alle gelesen" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/notifications/read-all")).toBe(true));

    await user.click(items[0]);
    expect(await screen.findByText("Dokumentseite")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/notifications/n1/read")).toBe(true);
  });
});

describe("Einstellungen Benachrichtigungen", () => {
  it("Uhrzeit ändern, Test-E-Mail, Push-Gerät entfernen", async () => {
    const device = {
      id: "p1",
      name: "Chrome auf Android",
      endpoint: "https://fcm.googleapis.com/x",
      created_at: "2026-10-01T10:00:00Z",
      last_success_at: null,
      last_error: "Push-Dienst meldet 403",
    };
    const { calls } = render(<NotificationSettingsSection />, [
      { path: "/api/v1/notifications/settings", body: settings({ push: true, push_devices: [device] }) },
      {
        method: "PATCH",
        path: "/api/v1/notifications/settings",
        body: settings({ digest_hour: 6, push: true, push_devices: [device] }),
      },
      {
        method: "POST",
        path: "/api/v1/notifications/test",
        body: { ok: true, message: "Test-E-Mail an admin@example.com verschickt." },
      },
      { method: "DELETE", path: "/api/v1/notifications/push-subscriptions/p1", body: settings() },
    ]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("combobox", { name: "Uhrzeit" }));
    await user.click(await screen.findByRole("option", { name: "06:00 Uhr", hidden: true }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ digest_hour: 6 }));

    await user.click(screen.getByRole("button", { name: "Test-E-Mail" }));
    expect(await screen.findByText("Test-E-Mail an admin@example.com verschickt.")).toBeInTheDocument();

    expect(screen.getByText("Fehler: Push-Dienst meldet 403")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Chrome auf Android entfernen" }));
    await waitFor(() => expect(screen.queryAllByTestId("push-device")).toHaveLength(0));
  });

  it("ohne eingerichteten E-Mail-Versand ist E-Mail gesperrt; ohne https kein Push", async () => {
    vi.stubGlobal("isSecureContext", false);
    render(<NotificationSettingsSection />, [
      { path: "/api/v1/notifications/settings", body: settings({ email_available: false }) },
    ]);
    const email = await screen.findByRole("switch", { name: /Per E-Mail/ });
    expect(email).toBeDisabled();
    expect(email).not.toBeChecked();
    expect(screen.getByText(/noch nicht eingerichtet/)).toBeInTheDocument();
    expect(screen.getByText(/nur über eine verschlüsselte Verbindung/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /einschalten/ })).not.toBeInTheDocument();
  });
});

describe("E-Mail-Versand (Admin)", () => {
  it("Anbieter vorbelegen, speichern ohne das Passwort erneut zu senden, Testmail", async () => {
    const saved = {
      configured: true,
      host: "mail.gmx.net",
      port: 587,
      security: "starttls",
      username: "familie@gmx.de",
      password_set: true,
      sender: "familie@gmx.de",
      app_url: "https://nas:8443",
      last_ok_at: null,
      last_error: "Anmeldung am Mailserver abgelehnt",
    };
    const { calls } = render(<MailSettingsCard />, [
      { path: "/api/v1/tenant/mail", body: saved },
      { method: "PUT", path: "/api/v1/tenant/mail", body: { ...saved, host: "smtp.web.de", last_error: null } },
      {
        method: "POST",
        path: "/api/v1/notifications/test",
        body: { ok: false, message: "Mailserver nicht erreichbar" },
      },
    ]);
    const user = userEvent.setup();
    expect(await screen.findByText("Anmeldung am Mailserver abgelehnt")).toBeInTheDocument();
    expect(screen.getByLabelText(/Server \(SMTP\)/)).toHaveValue("mail.gmx.net");

    await user.click(screen.getByRole("combobox", { name: "Anbieter (füllt Server und Port aus)" }));
    await user.click(await screen.findByRole("option", { name: "WEB.DE", hidden: true }));
    expect(screen.getByLabelText(/Server \(SMTP\)/)).toHaveValue("smtp.web.de");
    expect(screen.getByText(/WEB.DE: In den Einstellungen/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        host: "smtp.web.de",
        port: 587,
        security: "starttls",
        username: "familie@gmx.de",
        password: null,
        sender: "familie@gmx.de",
        app_url: "https://nas:8443",
      }),
    );
    await waitFor(() => expect(screen.queryByText("Anmeldung am Mailserver abgelehnt")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Test-E-Mail an mich" }));
    expect(await screen.findByText("Mailserver nicht erreichbar")).toBeInTheDocument();
  });
});
