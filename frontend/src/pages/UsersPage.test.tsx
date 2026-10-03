import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "../api/client";
import { RequireAuth } from "../components/RequireAuth";
import { me } from "../test/fixtures";
import { mockFetch, renderWithProviders } from "../test/render";
import { UsersPage } from "./UsersPage";

const member = (over: object = {}) => ({
  id: "u2",
  email: "anna@example.com",
  display_name: "Anna",
  role: "member",
  is_active: true,
  last_login_at: null,
  created_at: "2026-10-03T08:00:00Z",
  ...over,
});
const self = member({ id: me.id, email: me.email, display_name: me.display_name, role: "admin" });

function render(routes: Parameters<typeof mockFetch>[0]) {
  tokenStore.set("a", "r");
  const result = mockFetch([{ path: "/api/v1/auth/me", body: me }, ...routes]);
  renderWithProviders(
    <RequireAuth>
      <UsersPage />
    </RequireAuth>,
  );
  return result;
}

describe("UsersPage", () => {
  it("legt ein Mitglied an und zeigt die Zugangsdaten zum Weitergeben", async () => {
    const { calls } = render([
      { path: "/api/v1/users", body: [self] },
      {
        method: "POST",
        path: "/api/v1/users",
        status: 201,
        body: member({ email: "ben@example.com", display_name: "Ben" }),
      },
    ]);
    const user = userEvent.setup();
    expect(await screen.findByText(/Anna Muster \(du\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mitglied hinzufügen" }));
    await user.type(await screen.findByLabelText(/^Name/), "Ben");
    await user.type(screen.getByLabelText(/^E-Mail/), "ben@example.com");
    await user.click(screen.getByRole("button", { name: "Anlegen" }));

    const shown = await screen.findByTestId("credential-password");
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/v1/users");
    expect(post?.body).toMatchObject({ display_name: "Ben", email: "ben@example.com", role: "member" });
    // vorgeschlagenes Startpasswort wurde gesendet und wird angezeigt
    expect((post?.body as { password: string }).password).toMatch(/^[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}$/);
    expect(shown).toHaveTextContent((post?.body as { password: string }).password);
  });

  it("deaktiviert ein Mitglied erst nach Rückfrage; eigenes Konto hat keine Aktionen", async () => {
    const { calls } = render([
      { path: "/api/v1/users", body: [self, member()] },
      { method: "PATCH", path: "/api/v1/users/u2", body: member({ is_active: false }) },
    ]);
    const user = userEvent.setup();
    const cards = await screen.findAllByTestId("member");
    expect(within(cards[0]).queryByRole("button", { name: /Aktionen/ })).toBeNull();

    await user.click(within(cards[1]).getByRole("button", { name: "Aktionen für Anna" }));
    await user.click(await screen.findByRole("menuitem", { name: /Deaktivieren/ }));
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await user.click(await screen.findByRole("button", { name: "Deaktivieren" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/v1/users/u2")?.body).toEqual({
        is_active: false,
      }),
    );
  });
});
