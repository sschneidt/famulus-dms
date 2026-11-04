import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, renderWithProviders } from "../test/render";
import { PropertiesPage } from "./PropertiesPage";

const haus = { id: "p1", name: "Meersburg Seeweg 12a", street: "Seeweg 12a", postal_code: "88709", city: "Meersburg", document_count: 3 };
const gartenhaus = { id: "p2", name: "Gartenhaus", street: "", postal_code: "", city: "", document_count: 0 };

describe("PropertiesPage", () => {
  it("legt ein Objekt von Hand an - zuerst nur mit Namen", async () => {
    let list = [haus];
    const { calls } = mockFetch([
      { path: "/api/v1/properties", body: () => list },
      { method: "POST", path: "/api/v1/properties", status: 201, body: () => ((list = [haus, gartenhaus]), gartenhaus) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<PropertiesPage />);
    expect(await screen.findByText("Meersburg Seeweg 12a")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Objekt anlegen" }));
    const dialog = await screen.findByRole("dialog");
    const create = within(dialog).getByRole("button", { name: "Anlegen" });
    expect(create).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Name/), "Gartenhaus");
    expect(create).toBeEnabled();
    await user.click(create);

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Gartenhaus", street: "", postal_code: "", city: "" });
    expect(await screen.findByText("Gartenhaus")).toBeInTheDocument();
    expect(screen.getByText("0 Dokumente")).toBeInTheDocument(); // ohne Adresse nur die Anzahl
  });

  it("verlangt die Adresse ganz oder gar nicht", async () => {
    mockFetch([{ path: "/api/v1/properties", body: [] }]);
    const user = userEvent.setup();
    renderWithProviders(<PropertiesPage />);
    await user.click(await screen.findByRole("button", { name: "Objekt anlegen" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Name/), "Wohnung");
    await user.type(within(dialog).getByLabelText("Straße und Hausnummer"), "Seeweg 1");
    expect(within(dialog).getByRole("button", { name: "Anlegen" })).toBeDisabled();
    expect(within(dialog).getByText(/alle drei leer lassen/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Postleitzahl"), "88709");
    await user.type(within(dialog).getByLabelText("Ort"), "Meersburg");
    expect(within(dialog).getByRole("button", { name: "Anlegen" })).toBeEnabled();
  });
});