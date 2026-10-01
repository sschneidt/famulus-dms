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

  it("zeigt den Ablageort auf dem NAS", () => {
    mockFetch([{ path: "/api/v1/properties", body: [] }]);
    renderWithProviders(<MetadataPanel doc={detail()} />);
    expect(screen.getByText("Familie Muster/Rechnungen/2026/strom.pdf")).toBeInTheDocument();
  });
});
