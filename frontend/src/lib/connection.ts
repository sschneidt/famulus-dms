import { useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";

/** GET /setup/status (oeffentlich): eingerichtet? und wie Geraete der Verschluesselung vertrauen. */
export interface SetupStatus {
  bootstrapped: boolean;
  /** true = HomeDMS nutzt eine eigene Zertifizierungsstelle -> neue Geraete einmal einrichten */
  tls?: boolean;
  http_port?: number;
  https_port?: number;
}

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: () => call(api.GET("/api/v1/setup/status")) as unknown as Promise<SetupStatus>,
    staleTime: 60_000,
  });
}

/** Hilfeseite, ueber die ein neues Geraet dem HomeDMS-Zertifikat vertraut (cert_page.py). */
export function certificatePageUrl(status: SetupStatus | undefined): string | null {
  if (!status?.tls) return null;
  const port = status.http_port ?? 8000;
  return `http://${window.location.hostname}${port === 80 ? "" : `:${port}`}/zertifikat`;
}

/** Laeuft die Seite unverschluesselt ueber das Netz? (localhost zaehlt nicht) */
export function insecureConnection(): boolean {
  const { protocol, hostname } = window.location;
  return protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(hostname);
}
