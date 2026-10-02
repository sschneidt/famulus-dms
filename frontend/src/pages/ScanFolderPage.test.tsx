import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { RequireAuth } from "../components/RequireAuth";
import { me } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { ScanFolderPage } from "./ScanFolderPage";

const source = {
  id: "s1",
  type: "nas_watch_folder",
  path: "",
  is_active: true,
  last_scanned_at: "2026-10-02T08:15:00Z",
  waiting: 1,
  error: null,
  recent: [
    { at: "2026-10-02T08:15:00Z", file: "Scan_0815.pdf", status: "importiert", message: "", document_id: "d1" },
    {
      at: "2026-10-02T08:15:00Z",
      file: "Brief.docx",
      status: "fehler",
      message: "Dateityp .docx wird nicht unterstuetzt",
      document_id: null,
    },
  ],
};

describe("ScanFolderPage", () => {
  it("zeigt Status und letzte Importe, 'Jetzt prüfen' stoesst einen Durchlauf an", async () => {
    tokenStore.set("a", "r");
    const { calls } = mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/import-sources", body: [source] },
      { method: "POST", path: "/api/v1/import-sources/s1/scan-now", status: 202, body: { queued: true } },
    ]);
    const user = userEvent.setup();
    renderWithProviders(
      <RequireAuth>
        <ScanFolderPage />
      </RequireAuth>,
    );

    expect(await screen.findByRole("link", { name: "Scan_0815.pdf" })).toHaveAttribute("href", "/dokumente/d1");
    expect(screen.getByText("importiert")).toBeInTheDocument();
    expect(screen.getByText("Dateityp .docx wird nicht unterstuetzt")).toBeInTheDocument();
    expect(screen.getByText(/1 Datei wartet/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Jetzt prüfen" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/import-sources/s1/scan-now")).toBe(true));
  });
});
