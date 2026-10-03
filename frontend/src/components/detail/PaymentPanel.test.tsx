import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentDetail } from "../../api/client";
import { doc } from "../../test/fixtures";
import { mockFetch, renderWithProviders } from "../../test/render";
import { PaymentPanel } from "./PaymentPanel";

const detail = (o: Partial<DocumentDetail> = {}): DocumentDetail => ({
  ...doc(),
  ocr_text: "",
  ocr_language: "deu",
  page_count: 1,
  ...o,
});

describe("PaymentPanel", () => {
  it("'Keine Rechnung' entfernt Betrag und Zahlung", async () => {
    const { calls } = mockFetch([
      { method: "PATCH", path: "/api/v1/documents/d1", body: detail({ is_invoice: false }) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<PaymentPanel doc={detail({ is_invoice: true, payment_status: "offen" })} />);
    await user.click(screen.getByRole("button", { name: "Keine Rechnung" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_invoice: false }));
  });

  it("bei 'Keine Rechnung' gibt es keinen Zahlungsbereich", () => {
    mockFetch([]);
    renderWithProviders(<PaymentPanel doc={detail({ is_invoice: false, amount: 15000 })} />);
    expect(screen.queryByText("Zahlung")).not.toBeInTheDocument();
  });
});
