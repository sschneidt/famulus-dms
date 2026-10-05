import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { RequireAuth } from "../components/RequireAuth";
import { me } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { LanguagesPage } from "./LanguagesPage";

const language = (code: string, name: string, extra: Record<string, unknown> = {}) => ({
  code,
  name,
  installed: true,
  selected: false,
  required_by: [],
  active: false,
  status: "installed",
  error: null,
  ...extra,
});

const response = {
  effective: "deu+eng+rus",
  languages: [
    language("deu", "Deutsch", { selected: true, active: true }),
    language("eng", "English", { selected: true, active: true }),
    language("rus", "Русский", { required_by: ["Olga"], active: true }),
    language("fra", "Français", { installed: false, status: "" }),
    language("ita", "Italiano", { installed: false, selected: true, status: "missing" }),
  ],
};

function render(user = me) {
  tokenStore.set("a");
  const result = mockFetch([
    { path: "/api/v1/auth/me", body: user },
    { path: "/api/v1/ocr-languages", body: response },
    { method: "PUT", path: "/api/v1/ocr-languages", body: response },
    { method: "POST", path: "/api/v1/ocr-languages/install", body: response },
  ]);
  renderWithProviders(
    <RequireAuth>
      <LanguagesPage />
    </RequireAuth>,
  );
  return result;
}

describe("LanguagesPage", () => {
  it("zeigt Sprachpakete mit Status, Oberflaechensprachen sind fest dabei", async () => {
    render();
    expect(await screen.findByText("deu+eng+rus")).toBeInTheDocument();
    const russian = screen.getByRole("checkbox", { name: /Русский/ });
    expect(russian).toBeChecked();
    expect(russian).toBeDisabled();
    expect(screen.getByText("für die Oberfläche von Olga")).toBeInTheDocument();
    expect(screen.getByText("fehlt")).toBeInTheDocument();
    // nicht gewaehlte, nicht installierte Sprachen erst auf Wunsch
    expect(screen.queryByRole("checkbox", { name: /Français/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Weitere Sprachen (1)" })).toBeInTheDocument();
  });

  it("speichert die Auswahl und stoesst fehlende Downloads an", async () => {
    const { calls } = render();
    const user = userEvent.setup();
    await screen.findByText("deu+eng+rus");
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Weitere Sprachen (1)" }));
    await user.click(screen.getByRole("checkbox", { name: /Français/ }));
    await user.click(screen.getByRole("checkbox", { name: /English/ }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ languages: ["deu", "ita", "fra"] }),
    );

    await user.click(screen.getByRole("button", { name: "Fehlende Pakete laden" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/ocr-languages/install")).toBe(true),
    );
  });

  it("ist nur fuer Admins", async () => {
    render({ ...me, role: "member" });
    expect(
      await screen.findByText("Die Sprachen der Texterkennung können nur Administratoren ändern."),
    ).toBeInTheDocument();
  });
});
