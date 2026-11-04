import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentDetail } from "../../api/client";
import { doc } from "../../test/fixtures";
import { mockFetch, renderWithProviders } from "../../test/render";
import { MetadataPanel } from "./MetadataPanel";

const detail = (o: Partial<DocumentDetail> = {}): DocumentDetail => ({
  ...doc(),
  ocr_text: "",
  ocr_language: "deu",
  page_count: 1,
  ...o,
});

describe("MetadataPanel", () => {
  it("schickt nur geaenderte Felder - ein unveraenderter Titel wird nicht zum eigenen Titel", async () => {
    const { calls } = mockFetch([
      { path: "/api/v1/properties", body: [] },
      { method: "PATCH", path: "/api/v1/documents/d1", body: detail({ subject: "Stromrechnung August" }) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<MetadataPanel doc={detail()} />);

    const subject = screen.getByLabelText(/Betreff/);
    await user.clear(subject);
    await user.type(subject, "Stromrechnung August");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ subject: "Stromrechnung August" });
  });

  it("eigener Titel laesst sich wieder automatisch bilden", async () => {
    const { calls } = mockFetch([
      { path: "/api/v1/properties", body: [] },
      { method: "PATCH", path: "/api/v1/documents/d1", body: detail() },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<MetadataPanel doc={detail({ title: "Mein Titel", title_locked: true })} />);

    expect(screen.getByText("eigener Titel")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Automatisch benennen" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title_locked: false }));
  });

  it("legt ein getipptes, unbekanntes Objekt beim Speichern an und ordnet es zu", async () => {
    const { calls } = mockFetch([
      { path: "/api/v1/properties", body: [{ id: "p1", name: "Haus Seeweg", street: "", postal_code: "", city: "", document_count: 2 }] },
      {
        method: "POST",
        path: "/api/v1/properties",
        status: 201,
        body: { id: "p2", name: "Gartenhaus", street: "", postal_code: "", city: "", document_count: 0 },
      },
      { method: "PATCH", path: "/api/v1/documents/d1", body: detail({ property_id: "p2" }) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<MetadataPanel doc={detail()} />);

    const field = screen.getAllByLabelText("Objekt")[0];
    await user.click(field);
    await user.type(field, "Gartenhaus");
    await user.click(await screen.findByRole("option", { name: "„Gartenhaus“ neu anlegen" }));
    // Noch nichts angelegt - erst beim Speichern
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Gartenhaus" });
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ property_id: "p2" });
  });

  it("bietet bei einem vorhandenen Namen kein Neuanlegen an", async () => {
    mockFetch([
      { path: "/api/v1/properties", body: [{ id: "p1", name: "Haus Seeweg", street: "", postal_code: "", city: "", document_count: 2 }] },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<MetadataPanel doc={detail()} />);
    const field = screen.getAllByLabelText("Objekt")[0];
    await user.click(field);
    await user.type(field, "haus seeweg");
    expect(await screen.findByRole("option", { name: "Haus Seeweg" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /neu anlegen/ })).not.toBeInTheDocument();
  });
  it("zeigt den Ablageort auf dem NAS", () => {
    mockFetch([{ path: "/api/v1/properties", body: [] }]);
    renderWithProviders(<MetadataPanel doc={detail()} />);
    expect(screen.getByText("Familie Muster/Rechnungen/2026/strom.pdf")).toBeInTheDocument();
  });
});
