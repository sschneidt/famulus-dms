import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore, type Schemas } from "../api/client";
import { RequireAuth } from "../components/RequireAuth";
import { me } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { DiagnosePage } from "./DiagnosePage";

const diagnostics = {
  checked_at: "2026-10-03T10:00:00Z",
  overall: "error",
  components: [
    {
      key: "database",
      name: "Datenbank",
      status: "ok",
      summary: "PostgreSQL 16.2",
      details: [{ label: "Antwortzeit", value: "3 ms" }],
      hint: null,
      actions: [],
    },
    {
      key: "worker",
      name: "Worker (Hintergrundverarbeitung)",
      status: "ok",
      summary: "bereit",
      details: [{ label: "Arbeitsstränge aktiv", value: "2 von 2" }],
      hint: null,
      actions: [
        { id: "restart-worker", label: "Worker neu starten", confirm: "Laufende Aufträge werden abgebrochen." },
      ],
    },
    {
      key: "ai",
      name: "KI (Ollama)",
      status: "error",
      summary: "nicht erreichbar",
      details: [{ label: "Adresse", value: "http://localhost:11434" }],
      hint: "Ollama starten.",
      actions: [],
    },
  ],
  recent_failures: [
    { job_id: 7, task: "Einordnung", at: "2026-10-03T09:00:00Z", document_id: "d1", document_title: "Kreditvertrag" },
  ],
};

const noBackups: Schemas["BackupsResponse"] = {
  available: true,
  folder: "/volume1/famulus/backups",
  keep: 5,
  items: [],
};

describe("DiagnosePage", () => {
  it("zeigt den Zustand aller Bausteine und startet den Worker erst nach Rückfrage neu", async () => {
    tokenStore.set("a");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/system/diagnostics", body: diagnostics },
      { path: "/api/v1/system/backups", body: noBackups },
      { method: "POST", path: "/api/v1/system/actions/restart-worker", body: { message: "Der Worker startet neu." } },
    ]);
    renderWithProviders(
      <RequireAuth>
        <DiagnosePage />
      </RequireAuth>,
    );

    expect(await screen.findByText("1 Baustein braucht Aufmerksamkeit")).toBeInTheDocument();
    const ai = screen.getByTestId("component-ai");
    expect(within(ai).getByText("Fehler")).toBeInTheDocument();
    expect(within(ai).getByText("Ollama starten.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kreditvertrag" })).toHaveAttribute("href", "/dokumente/d1");

    const user = userEvent.setup();
    await user.click(
      within(screen.getByTestId("component-worker")).getByRole("button", { name: "Worker neu starten" }),
    );
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    expect(await screen.findByText("Laufende Aufträge werden abgebrochen.")).toBeInTheDocument();
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Worker neu starten" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/system/actions/restart-worker")).toBe(true),
    );
    expect(await screen.findByText("Der Worker startet neu.")).toBeInTheDocument();
  });

  it("legt eine Datenbanksicherung an und löscht sie erst nach Rückfrage", async () => {
    tokenStore.set("a");
    const item = { name: "homedms-0.2.1-20261019-101500.dump", size: 2_411_520, created: "2026-10-19T10:15:00Z" };
    let state = noBackups;
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/system/diagnostics", body: diagnostics },
      { method: "GET", path: "/api/v1/system/backups", body: () => state },
      {
        method: "POST",
        path: "/api/v1/system/backups",
        status: 201,
        body: () => (state = { ...noBackups, items: [item] }),
      },
      {
        method: "DELETE",
        path: `/api/v1/system/backups/${item.name}`,
        body: () => (state = noBackups),
      },
    ]);
    renderWithProviders(
      <RequireAuth>
        <DiagnosePage />
      </RequireAuth>,
    );

    const section = await screen.findByTestId("backups");
    expect(await within(section).findByText("Noch keine Sicherung vorhanden.")).toBeInTheDocument();
    expect(within(section).getByText(/\/volume1\/famulus\/backups/)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(within(section).getByRole("button", { name: "Jetzt sichern" }));
    expect(await within(section).findByText(item.name)).toBeInTheDocument();
    expect(within(section).getByText(/2,3 MB/)).toBeInTheDocument();
    expect(await screen.findByText("Sicherung angelegt.")).toBeInTheDocument();

    await user.click(within(section).getByRole("button", { name: `Löschen ${item.name}` }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(await screen.findByText(`Die Sicherung ${item.name} wird endgültig gelöscht.`)).toBeInTheDocument();
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await within(section).findByText("Noch keine Sicherung vorhanden.")).toBeInTheDocument();
  });

  it("zeigt einen Hinweis und sperrt den Knopf, wenn pg_dump fehlt", async () => {
    tokenStore.set("a");
    mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/system/diagnostics", body: diagnostics },
      { path: "/api/v1/system/backups", body: { ...noBackups, available: false } },
    ]);
    renderWithProviders(
      <RequireAuth>
        <DiagnosePage />
      </RequireAuth>,
    );
    const section = await screen.findByTestId("backups");
    expect(await within(section).findByText(/Programm pg_dump/)).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Jetzt sichern" })).toBeDisabled();
  });});
