import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
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

describe("DiagnosePage", () => {
  it("zeigt den Zustand aller Bausteine und startet den Worker erst nach Rückfrage neu", async () => {
    tokenStore.set("a", "r");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/system/diagnostics", body: diagnostics },
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
    const confirm = screen.getAllByRole("button", { name: "Worker neu starten" });
    await user.click(confirm[confirm.length - 1]);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/system/actions/restart-worker")).toBe(true),
    );
    expect(await screen.findByText("Der Worker startet neu.")).toBeInTheDocument();
  });
});
