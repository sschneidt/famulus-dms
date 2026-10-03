import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, call, onSessionExpired, tokenStore, type Me } from "../api/client";

type AuthState =
  { status: "loading"; user: null } | { status: "anonymous"; user: null } | { status: "authenticated"; user: Me };

interface AuthContextValue {
  state: AuthState;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
  /** Angaben zum Nutzer neu laden (z. B. nach Aendern des Anzeigenamens) */
  refresh(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const loadMe = useCallback(async () => {
    if (!tokenStore.access) {
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
    async (email: string, password: string) => {
      const tokens = await call(api.POST("/api/v1/auth/login", { body: { email, password } }));
      tokenStore.set(tokens.access_token, tokens.refresh_token);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    const refresh = tokenStore.refresh;
    if (refresh) {
      // Refresh-Token serverseitig widerrufen - Fehler hier sind egal, lokal wird ohnehin abgemeldet
      await api.POST("/api/v1/auth/logout", { body: { refresh_token: refresh } }).catch(() => undefined);
    }
    tokenStore.clear();
    queryClient.clear();
    setState({ status: "anonymous", user: null });
  }, [queryClient]);

  const value = useMemo(() => ({ state, login, logout, refresh: loadMe }), [state, login, logout, loadMe]);
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
