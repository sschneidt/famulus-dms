import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { RequireAuth } from "../components/RequireAuth";
import { categories, doc, me, page } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { ReviewPage } from "./ReviewPage";

const unanalyzed = (aiAvailable: boolean) => ({
  total: 2,
  ai_available: aiAvailable,
  items: [
    {
      ...doc({ id: "d1", title: "Kreditvertrag", classification_status: "needs_review" }),
      classification_error: "KI nicht erreichbar: Verbindung abgelehnt",
      reasons: ["Kategorie: KI war nicht erreichbar", "Betreff, Absender, Fristen: KI war nicht erreichbar"],
    },
    { ...doc({ id: "d2", title: "Scan_0815.pdf", ocr_status: "failed" }), reasons: ["Texterkennung fehlgeschlagen"] },
  ],
});

function render(aiAvailable: boolean) {
  tokenStore.set("a");
  const result = mockFetch([
    { path: "/api/v1/auth/me", body: me },
    { path: "/api/v1/categories", body: categories },
    { path: "/api/v1/documents/needs-review", body: page([]) },
    { path: "/api/v1/documents/unanalyzed", body: unanalyzed(aiAvailable) },
    { method: "POST", path: "/api/v1/documents/unanalyzed/analyze", body: { queued: 2, jobs: 3 } },
  ]);
  renderWithProviders(
    <RequireAuth>
      <ReviewPage />
    </RequireAuth>,
  );
  return result;
}

describe("ReviewPage – Nicht analysiert", () => {
  it("zeigt fehlende Schritte und holt mit 'Alle analysieren' alles nach", async () => {
    const { calls } = render(true);
    // nichts zu prüfen -> gleich die Ansicht mit Arbeit
    const cards = await screen.findAllByTestId("unanalyzed");
    expect(within(cards[0]).getByText("Kategorie: KI war nicht erreichbar")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Texterkennung fehlgeschlagen")).toBeInTheDocument();
    expect(screen.queryByText("Die KI antwortet gerade nicht")).toBeNull();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Alle analysieren (2)" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/documents/unanalyzed/analyze")).toBe(true),
    );
    expect(await screen.findByText(/2 Dokumente werden analysiert/)).toBeInTheDocument();
  });

  it("warnt, wenn die KI gerade nicht antwortet", async () => {
    render(false);
    expect(await screen.findByText("Die KI antwortet gerade nicht")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Alle analysieren (2)" })).toBeEnabled();
  });
});
