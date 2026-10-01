import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { doc } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { UnpaidPage } from "./UnpaidPage";

describe("UnpaidPage", () => {
  it("zeigt Summe, markiert Ueberfaelliges und traegt die Zahlung mit Datum ein", async () => {
    const overdue = dayjs().subtract(5, "day").format("YYYY-MM-DD");
    const { calls } = mockFetch([
      {
        path: "/api/v1/documents/unpaid",
        body: {
          items: [
            doc({ id: "d1", title: "Handwerker", amount: 380, payment_status: "offen", payment_due: overdue }),
            doc({ id: "d2", title: "Strom", amount: 42.5, payment_status: "offen", payment_due: null }),
          ],
          total: 2,
          total_amount: 422.5,
        },
      },
      { method: "PATCH", path: "/api/v1/documents/d1", body: doc({ payment_status: "bezahlt" }) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<UnpaidPage />);

    expect((await screen.findByTestId("unpaid-sum")).textContent?.replace(/\s/g, " ")).toBe("422,50 €");
    const [first, second] = screen.getAllByTestId("unpaid-item");
    expect(within(first).getByText(/seit 5 Tagen überfällig/)).toBeInTheDocument();
    expect(within(second).getByText("ohne Zahlungsfrist")).toBeInTheDocument();

    await user.click(within(first).getByRole("button", { name: "Bezahlt" }));
    await user.click(await screen.findByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        payment_status: "bezahlt",
        paid_on: dayjs().format("YYYY-MM-DD"),
      }),
    );
  });

  it("leer: alles bezahlt", async () => {
    mockFetch([{ path: "/api/v1/documents/unpaid", body: { items: [], total: 0, total_amount: 0 } }]);
    renderWithProviders(<UnpaidPage />);
    expect(await screen.findByText("Alles bezahlt")).toBeInTheDocument();
  });
});
