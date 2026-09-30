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
    renderWithProviders(<WiedervorlageCard wv={wv({ status: "offen", due_date: due, recurrence: "yearly" })} />);

    expect(screen.getByText("seit 3 Tagen überfällig")).toBeInTheDocument();
    expect(screen.getByTestId("wiedervorlage")).toHaveAttribute("data-overdue", "true");
    expect(screen.getByText("jährlich")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Erledigt" }));
    expect(await screen.findByText("Erledigt – nächster Termin am 15.10.2027")).toBeInTheDocument();
  });
});
