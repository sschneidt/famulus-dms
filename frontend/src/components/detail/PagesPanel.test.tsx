import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentDetail } from "../../api/client";
import { doc } from "../../test/fixtures";
import { mockFetch, renderWithProviders } from "../../test/render";
import { PagesPanel } from "./PagesPanel";

const detail = (o: Partial<DocumentDetail> = {}): DocumentDetail => ({
  ...doc(),
  ocr_text: "",
  ocr_language: "deu",
  page_count: 3,
  ...o,
});

describe("PagesPanel", () => {
  it("zeigt Seiten und schickt die neue Reihenfolge", async () => {
    const { calls } = mockFetch([{ method: "PUT", path: "/api/v1/documents/d1/pages/order", body: { page_count: 3 } }]);
    const user = userEvent.setup();
    renderWithProviders(<PagesPanel doc={detail()} />);

    expect(screen.getAllByTestId("page")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Seite 1 nach vorn" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Seite 3 nach vorn" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ order: [1, 3, 2] }));
  });

  it("waehrend der Verarbeitung gesperrt, einseitig ohne Sortierknoepfe", () => {
    mockFetch([]);
    renderWithProviders(<PagesPanel doc={detail({ ocr_status: "pending", page_count: 1 })} />);
    expect(screen.getByRole("button", { name: "Seite hinzufügen" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /nach vorn/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Text wird erkannt/)).toBeInTheDocument();
  });
});
