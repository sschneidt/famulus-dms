import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { mockFetch, renderWithProviders } from "../test/render";
import { wv } from "../test/fixtures";
import { WiedervorlageCard } from "./WiedervorlageCard";

describe("WiedervorlageCard", () => {
  it("KI-Vorschlag zeigt Fundstelle und laesst sich uebernehmen", async () => {
    const { calls } = mockFetch([
      { method: "POST", path: "/api/v1/wiedervorlagen/w1/confirm", body: wv({ status: "offen" }) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<WiedervorlageCard wv={wv()} showDocument />);

    expect(screen.getByText("zahlbar bis 15.10.2026")).toBeInTheDocument();
    expect(screen.getByTestId("wiedervorlage")).not.toHaveAttribute("data-overdue");
    expect(screen.getByText("Stromrechnung September")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Übernehmen" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/w1/confirm"))).toBe(true));
    expect(await screen.findByText("Termin übernommen")).toBeInTheDocument();
  });

  it("ueberfaelliger offener Termin wird markiert und meldet beim Erledigen den Folgetermin", async () => {
    const due = dayjs().subtract(3, "day").format("YYYY-MM-DD");
    mockFetch([
      {
        method: "POST",
        path: "/api/v1/wiedervorlagen/w1/complete",
        body: {
          completed: wv({ status: "erledigt" }),
          next: wv({ id: "w2", status: "offen", due_date: "2027-10-15" }),
        },
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(
      <WiedervorlageCard
        wv={wv({ status: "offen", due_date: due, recurrence: "yearly", note: "Kündigungsfrist prüfen" })}
      />,
    );

    expect(screen.getByText("seit 3 Tagen überfällig")).toBeInTheDocument();
    expect(screen.getByTestId("wiedervorlage")).toHaveAttribute("data-overdue", "true");
    expect(screen.getByText("jährlich")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Erledigt" }));
    expect(await screen.findByText("Erledigt – nächster Termin am 15.10.2027")).toBeInTheDocument();
  });

  it("Zahlungsfrist: 'Bezahlt' fragt das Zahlungsdatum ab (vorbelegt mit heute)", async () => {
    const today = dayjs().format("YYYY-MM-DD");
    const { calls } = mockFetch([
      {
        method: "POST",
        path: "/api/v1/wiedervorlagen/w1/complete",
        body: { completed: wv({ status: "erledigt" }), next: null },
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<WiedervorlageCard wv={wv({ status: "offen" })} />);

    expect(screen.queryByRole("button", { name: "Erledigt" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bezahlt" }));
    const save = await screen.findByRole("button", { name: "Speichern" });
    expect(screen.getByLabelText("Zahlungsdatum")).toHaveValue(dayjs().format("DD.MM.YYYY"));
    await user.click(save);
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/w1/complete"))?.body).toEqual({ paid_on: today }));
    expect(await screen.findByText(`Bezahlt am ${dayjs().format("DD.MM.YYYY")}`)).toBeInTheDocument();
  });

  it("vorgeschlagene Zahlungsfrist: 'Schon bezahlt' markiert das Dokument als bezahlt", async () => {
    const { calls } = mockFetch([{ method: "PATCH", path: "/api/v1/documents/d1", body: {} }]);
    const user = userEvent.setup();
    renderWithProviders(<WiedervorlageCard wv={wv()} />);
    await user.click(screen.getByRole("button", { name: "Schon bezahlt" }));
    await user.click(await screen.findByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        payment_status: "bezahlt",
        paid_on: dayjs().format("YYYY-MM-DD"),
      }),
    );
  });

  it("'Keine Rechnung': Zahlungsfrist ist ein normaler Termin (Erledigt statt Bezahlt)", () => {
    mockFetch([]);
    renderWithProviders(<WiedervorlageCard wv={wv({ status: "offen", document_is_invoice: false })} />);
    expect(screen.getByRole("button", { name: "Erledigt" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bezahlt" })).not.toBeInTheDocument();
  });
});
