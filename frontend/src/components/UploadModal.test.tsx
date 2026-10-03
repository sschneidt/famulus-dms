import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockFetch, renderWithProviders } from "../test/render";
import { UploadModal } from "./UploadModal";

// Inhalt = Kennung (jsdom gibt Dateinamen beim Senden nicht weiter, Inhalte schon)
const foto = (name: string) => new File([`INHALT-${name}`], name, { type: "image/jpeg" });

/** Hochgeladene Dateien (in Reihenfolge) aus den protokollierten Multipart-Uploads */
function uploadedNames(calls: { method: string; path: string; body: unknown }[]): string[][] {
  return calls
    .filter((c) => c.method === "POST" && c.path === "/api/v1/documents")
    .map((c) => [...String(c.body).matchAll(/INHALT-([\w.-]+)/g)].map((m) => m[1]));
}

describe("UploadModal", () => {
  it("mehrere Fotos werden standardmaessig EIN Dokument, Reihenfolge laesst sich aendern", async () => {
    const { calls } = mockFetch([{ method: "POST", path: "/api/v1/documents", status: 201, body: { id: "neu" } }]);
    const user = userEvent.setup();
    renderWithProviders(
      <UploadModal
        opened
        onClose={vi.fn()}
        initialFiles={[
          { file: foto("seite-a.jpg"), source: "photo_app" },
          { file: foto("seite-b.jpg"), source: "photo_app" },
        ]}
      />,
    );

    expect(await screen.findByText("Ein Dokument (2 Seiten)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Seite 2 nach oben" }));
    await user.click(screen.getByRole("button", { name: "Als ein Dokument hochladen" }));
    await waitFor(() => expect(uploadedNames(calls)).toEqual([["seite-b.jpg", "seite-a.jpg"]]));
  });

  it("auf 'einzelne Dokumente' umgestellt: ein Upload je Datei", async () => {
    const { calls } = mockFetch([{ method: "POST", path: "/api/v1/documents", status: 201, body: { id: "neu" } }]);
    const user = userEvent.setup();
    renderWithProviders(
      <UploadModal
        opened
        onClose={vi.fn()}
        initialFiles={[
          { file: foto("a.jpg"), source: "photo_app" },
          { file: foto("b.jpg"), source: "photo_app" },
        ]}
      />,
    );
    await user.click(await screen.findByText("2 einzelne Dokumente"));
    await user.click(screen.getByRole("button", { name: "2 Dokumente hochladen" }));
    await waitFor(() => expect(uploadedNames(calls)).toEqual([["a.jpg"], ["b.jpg"]]));
  });

  it("Foto wird gleich zugeschnitten: Vorschau hochladen, ohne erneuten Zuschnitt", async () => {
    const { calls } = mockFetch([
      {
        method: "POST",
        path: "/api/v1/photos/rectify",
        raw: "INHALT-zugeschnitten.jpg",
        headers: { "Content-Type": "image/jpeg", "X-Cropped": "true", "X-Skew": "0.0" },
      },
      { method: "POST", path: "/api/v1/documents", status: 201, body: { id: "neu" } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(
      <UploadModal opened onClose={vi.fn()} initialFiles={[{ file: foto("tisch.jpg"), source: "photo_app" }]} />,
    );
    expect(await screen.findByText("Zugeschnitten")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    await waitFor(() => expect(uploadedNames(calls)).toEqual([["zugeschnitten.jpg"]]));
    expect(autoCropFlags(calls)).toEqual([["false"]]);
  });

  it("'Original verwenden' laedt das unveraenderte Foto hoch", async () => {
    const { calls } = mockFetch([
      {
        method: "POST",
        path: "/api/v1/photos/rectify",
        raw: "INHALT-zugeschnitten.jpg",
        headers: { "Content-Type": "image/jpeg", "X-Cropped": "true", "X-Skew": "0.0" },
      },
      { method: "POST", path: "/api/v1/documents", status: 201, body: { id: "neu" } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(
      <UploadModal opened onClose={vi.fn()} initialFiles={[{ file: foto("tisch.jpg"), source: "photo_app" }]} />,
    );
    await user.click(await screen.findByRole("button", { name: "Original verwenden" }));
    expect(screen.getByText("Original")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    await waitFor(() => expect(uploadedNames(calls)).toEqual([["tisch.jpg"]]));
    expect(autoCropFlags(calls)).toEqual([["false"]]);
  });

  it("Vorschau nicht moeglich: Original hochladen, Server schneidet zu", async () => {
    const { calls } = mockFetch([
      { method: "POST", path: "/api/v1/photos/rectify", status: 500, body: { detail: "kaputt" } },
      { method: "POST", path: "/api/v1/documents", status: 201, body: { id: "neu" } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(
      <UploadModal opened onClose={vi.fn()} initialFiles={[{ file: foto("tisch.jpg"), source: "photo_app" }]} />,
    );
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/photos/rectify")).toBe(true));
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    await waitFor(() => expect(uploadedNames(calls)).toEqual([["tisch.jpg"]]));
    expect(autoCropFlags(calls)).toEqual([["true"]]);
  });
});

function autoCropFlags(calls: { method: string; path: string; body: unknown }[]): string[][] {
  return calls
    .filter((c) => c.method === "POST" && c.path === "/api/v1/documents")
    .map((c) => [...String(c.body).matchAll(/name="auto_crop"\r?\n\r?\n(\w+)/g)].map((m) => m[1]));
}
