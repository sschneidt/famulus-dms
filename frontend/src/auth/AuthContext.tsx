import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, authFetch, call, onSessionExpired, SESSION_HEADER, tokenStore, type Me } from "../api/client";

type AuthState =
  { status: "loading"; user: null } | { status: "anonymous"; user: null } | { status: "authenticated"; user: Me };

/** Ergebnis von login(): fertig - oder es fehlt noch der Code aus der Authenticator-App. */
export type LoginResult = { status: "ok"; notice?: string | null } | { status: "two-factor"; challenge: string };

interface AuthContextValue {
  state: AuthState;
  login(email: string, password: string): Promise<LoginResult>;
  /** Zweiter Schritt der Zwei-Faktor-Anmeldung; liefert ggf. einen Hinweis (z. B. Wiederherstellungscodes). */
  completeTwoFactor(challenge: string, code: string): Promise<string | null>;
  logout(): Promise<void>;
  /** Angaben zum Nutzer neu laden (z. B. nach Aendern des Anzeigenamens) */
  refresh(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const loadMe = useCallback(async () => {
    // Nach dem Neuladen liegt kein Access-Token im Speicher - per HttpOnly-Cookie fortsetzen
    if (!tokenStore.access && tokenStore.hasSession) await authFetch.restore(window.location.origin);
    if (!tokenStore.access) {
      tokenStore.clear();
      setState({ status: "anonymous", user: null });
      return;
    }
    try {
      const user = await call(api.GET("/api/v1/auth/me"));
      setState({ status: "authenticated", user });
    } catch {
      tokenStore.clear();
      setState({ status: "anonymous", user: null });
    }
  }, []);

  useEffect(() => {
    void loadMe();
    return onSessionExpired(() => {
      queryClient.clear();
      setState({ status: "anonymous", user: null });
    });
  }, [loadMe, queryClient]);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const result = await call(api.POST("/api/v1/auth/login", { body: { email, password }, headers: SESSION_HEADER }));
      if (result.two_factor_required && result.challenge) return { status: "two-factor", challenge: result.challenge };
      tokenStore.set(result.access_token);
      await loadMe();
      return { status: "ok", notice: result.notice };
    },
    [loadMe],
  );

  const completeTwoFactor = useCallback(
    async (challenge: string, code: string) => {
      const result = await call(
        api.POST("/api/v1/auth/login/2fa", { body: { challenge, code }, headers: SESSION_HEADER }),
      );
      tokenStore.set(result.access_token);
      await loadMe();
      return result.notice ?? null;
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    // Sitzung serverseitig beenden (Cookie) - Fehler hier sind egal, lokal wird ohnehin abgemeldet
    await api.POST("/api/v1/auth/logout", { headers: SESSION_HEADER }).catch(() => undefined);
    tokenStore.clear();
    queryClient.clear();
    setState({ status: "anonymous", user: null });
  }, [queryClient]);

  const value = useMemo(
    () => ({ state, login, completeTwoFactor, logout, refresh: loadMe }),
    [state, login, completeTwoFactor, logout, loadMe],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth ausserhalb von AuthProvider");
  return ctx;
}

/** Nur innerhalb geschuetzter Seiten verwenden (dort ist der Nutzer garantiert angemeldet). */
export function useUser(): Me {
  const { state } = useAuth();
  if (state.status !== "authenticated") throw new Error("nicht angemeldet");
  return state.user;
}
