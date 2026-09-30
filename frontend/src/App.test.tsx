import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { tokenStore } from "./api/client";
import { routes } from "./routes";
import { categories, doc, me, page, wv } from "./test/fixtures";
import { mockFetch, renderWithProviders } from "./test/render";

describe("App (angemeldet)", () => {
  it("zeigt Dokumentliste, Kategorien und Zaehler in der Navigation", async () => {
    tokenStore.set("a", "r");
    mockFetch([
      { path: "/api/v1/auth/me", body: me },
      { path: "/api/v1/categories", body: categories },
      {
        path: "/api/v1/documents",
        body: page([
          doc(),
          doc({ id: "d2", title: "Kfz-Versicherung", category_id: "c-vers", classification_status: "needs_review" }),
        ]),
      },
      { path: "/api/v1/documents/needs-review", body: page([doc({ id: "d2" })]) },
      { path: "/api/v1/wiedervorlagen", body: page([wv()]) },
    ]);
    renderWithProviders(<></>, { routes });

    expect(await screen.findByText("Stromrechnung September")).toBeInTheDocument();
    expect(screen.getByText("Kfz-Versicherung")).toBeInTheDocument();
    expect(await within(screen.getByRole("table")).findByText("Rechnungen")).toBeInTheDocument();
    expect(screen.getByText("2 Dokumente")).toBeInTheDocument();
    const nav = screen.getByRole("link", { name: /Prüfen/ });
    expect(await within(nav).findByText("1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Aufbewahrung/ })).toBeInTheDocument(); // Admin
  });

  it("leitet ohne Anmeldung zur Login-Seite", async () => {
    mockFetch([{ path: "/api/v1/setup/status", body: { bootstrapped: true } }]);
    renderWithProviders(<></>, { routes, path: "/termine" });
    expect(await screen.findByRole("button", { name: "Anmelden" })).toBeInTheDocument();
  });
});
