/**
 * API-Client fuer das HomeDMS-Backend.
 *
 * - Typen kommen aus der OpenAPI-Beschreibung des Backends (schema.d.ts, erzeugt mit
 *   `npm run gen:api`) - aendert sich das Backend, meldet der TypeScript-Compiler die Stellen.
 * - authFetch haengt das Zugangs-Token an. Ist es abgelaufen (401), wird es einmal mit dem
 *   Refresh-Token erneuert und die Anfrage wiederholt. Mehrere gleichzeitige Anfragen teilen sich
 *   dabei EINE Erneuerung (sonst wuerde das rotierende Refresh-Token sich selbst entwerten).
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type DocumentItem = Schemas["DocumentResponse"];
export type DocumentDetail = Schemas["DocumentDetailResponse"];
export type Category = Schemas["CategoryResponse"];
export type Wiedervorlage = Schemas["WiedervorlageResponse"];
export type Me = Schemas["MeResponse"];
export type Property = Schemas["PropertyResponse"];

const SESSION_KEY = "homedms.session"; // nur "1" = es gibt eine Anmeldung (kein Geheimnis)
const LEGACY_KEYS = ["homedms.accessToken", "homedms.refreshToken"]; // frueher im Browser-Speicher
const REFRESH_PATH = "/api/v1/auth/refresh";
/** Kennzeichnet die Weboberflaeche: das Refresh-Token kommt dann nur als HttpOnly-Cookie. */
export const SESSION_HEADER = { "X-HomeDMS-Session": "cookie" } as const;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // z. B. privater Modus mit gesperrtem Speicher
  }
}

// Aeltere Versionen hatten die Tokens im Browser-Speicher - dort sind sie fuer jedes Skript lesbar.
for (const key of LEGACY_KEYS) storage()?.removeItem(key);

/**
 * Sicherheit (docs/Sicherheitskonzept.md): Das Access-Token (15 Min.) liegt nur im Arbeitsspeicher
 * dieser Seite, das Refresh-Token als HttpOnly-Cookie, das kein Skript lesen kann. Nach einem
 * Neuladen holt sich die Seite per Cookie ein neues Access-Token.
 */
let accessToken: string | null = null;

export const tokenStore = {
  get access(): string | null {
    return accessToken;
  },
  /** Gibt es (vermutlich) eine Anmeldung, die sich per Cookie erneuern laesst? */
  get hasSession(): boolean {
    return storage()?.getItem(SESSION_KEY) === "1";
  },
  set(access: string) {
    accessToken = access;
    storage()?.setItem(SESSION_KEY, "1");
  },
  clear() {
    accessToken = null;
    storage()?.removeItem(SESSION_KEY);
  },
};

// Wird aufgerufen, wenn auch die Erneuerung scheitert -> Anmeldung ist abgelaufen.
const sessionExpiredListeners = new Set<() => void>();
export function onSessionExpired(listener: () => void): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

const NO_REFRESH = new Set([REFRESH_PATH, "/api/v1/auth/login", "/api/v1/auth/login/2fa", "/api/v1/auth/logout"]);

export function createAuthFetch(baseFetch: typeof fetch = (...args) => fetch(...args)) {
  let refreshing: Promise<boolean> | null = null;

  /** Neues Access-Token per HttpOnly-Cookie holen. Mehrere gleichzeitige Anfragen teilen sich EINE
   * Erneuerung (das Refresh-Token rotiert - ein zweiter Versuch mit dem alten waere ungueltig). */
  async function refreshTokens(origin: string): Promise<boolean> {
    refreshing ??= (async () => {
      try {
        const resp = await baseFetch(new URL(REFRESH_PATH, origin), {
          method: "POST",
          headers: SESSION_HEADER,
          credentials: "same-origin",
        });
        if (!resp.ok) return false;
        const data = (await resp.json()) as { access_token: string };
        tokenStore.set(data.access_token);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  function withToken(request: Request): Request {
    const headers = new Headers(request.headers);
    const token = tokenStore.access;
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return new Request(request, { headers });
  }

  const authFetch = async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const original = input instanceof Request && !init ? input : new Request(input, init);
    const retryCopy = original.clone(); // der Body laesst sich nur einmal lesen
    const url = new URL(original.url);
    // Nach dem Neuladen: erst per Cookie ein Access-Token holen, statt sicher an 401 zu scheitern
    if (!tokenStore.access && tokenStore.hasSession && !NO_REFRESH.has(url.pathname)) {
      await refreshTokens(url.origin);
    }
    const response = await baseFetch(withToken(original));
    if (response.status !== 401 || NO_REFRESH.has(url.pathname) || !tokenStore.hasSession) {
      return response;
    }
    if (await refreshTokens(url.origin)) {
      return baseFetch(withToken(retryCopy));
    }
    tokenStore.clear();
    sessionExpiredListeners.forEach((listener) => listener());
    return response;
  };
  /** Fuer den Start der App: gibt es eine Anmeldung, die sich per Cookie fortsetzen laesst? */
  authFetch.restore = (origin: string) => refreshTokens(origin);
  return authFetch;
}

export const authFetch = createAuthFetch();

export const api = createClient<paths>({
  baseUrl: typeof window !== "undefined" ? window.location.origin : "http://localhost",
  fetch: authFetch,
});

/** Fehler mit verstaendlicher Meldung aus der Backend-Antwort ({"detail": ...}). */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function messageFrom(error: unknown, status: number): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI-Validierungsfehler: [{loc: [...], msg: "..."}]
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
      .join("; ");
  }
  if (status === 0) return "Server nicht erreichbar";
  return `Fehler ${status}`;
}

/** Ergebnis eines api.GET/POST/...-Aufrufs auspacken oder ApiError werfen. */
export async function call<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request;
  if (error !== undefined || !response.ok) {
    throw new ApiError(response.status, messageFrom(error, response.status));
  }
  return data as T;
}

/** Datei eines Dokuments mit Anmeldung laden (fuer Vorschau und Download). */
export async function fetchDocumentFile(documentId: string): Promise<Blob> {
  const resp = await authFetch(`${api_base()}/api/v1/documents/${documentId}/download`);
  if (!resp.ok) throw new ApiError(resp.status, `Datei konnte nicht geladen werden (${resp.status})`);
  return resp.blob();
}

function api_base(): string {
  return typeof window !== "undefined" ? window.location.origin : "http://localhost";
}

export interface UploadOptions {
  title?: string;
  /** "photo_app" fuer Kamera-Aufnahmen, sonst "upload" */
  source?: Schemas["DocumentSource"];
  originalPresent?: Schemas["OriginalPresent"];
  originalLocation?: string;
  /** je Datei (gleiche Reihenfolge): Foto vom Server zuschneiden lassen? Standard ja */
  autoCrop?: boolean[];
}

/** Multipart-Upload (openapi-fetch kuemmert sich nicht um FormData-Bodies).
 *  Mehrere Dateien werden im Backend zu EINEM Dokument mit mehreren Seiten zusammengefasst. */
export async function uploadDocument(files: File | File[], options: UploadOptions = {}): Promise<DocumentItem> {
  const form = new FormData();
  for (const file of Array.isArray(files) ? files : [files]) form.append("file", file);
  if (options.title) form.append("title", options.title);
  if (options.source) form.append("source", options.source);
  if (options.originalPresent) form.append("original_present", options.originalPresent);
  if (options.originalLocation) form.append("original_location", options.originalLocation);
  // je Datei: false = schon per Vorschau aufbereitet bzw. Original gewuenscht; fehlt = Server schneidet zu
  for (const crop of options.autoCrop ?? []) form.append("auto_crop", String(crop));
  const resp = await authFetch(`${api_base()}/api/v1/documents`, { method: "POST", body: form });
  if (!resp.ok) {
    let error: unknown;
    try {
      error = await resp.json();
    } catch {
      /* keine JSON-Antwort */
    }
    throw new ApiError(resp.status, messageFrom(error, resp.status));
  }
  return resp.json();
}

async function sendForm(path: string, method: string, form?: FormData, json?: unknown) {
  const resp = await authFetch(`${api_base()}${path}`, {
    method,
    body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
    headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
  });
  if (!resp.ok) {
    let error: unknown;
    try {
      error = await resp.json();
    } catch {
      /* keine JSON-Antwort */
    }
    throw new ApiError(resp.status, messageFrom(error, resp.status));
  }
  return resp.json() as Promise<{ page_count: number }>;
}

/** Seiten hinzufuegen (PDF oder Bilder), position = vor dieser Seite (1-basiert), sonst ans Ende. */
export function addPages(documentId: string, files: File[], position?: number) {
  const form = new FormData();
  for (const file of files) form.append("file", file);
  if (position) form.append("position", String(position));
  return sendForm(`/api/v1/documents/${documentId}/pages`, "POST", form);
}

/** Eine Foto-/Scan-Seite nachtraeglich zuschneiden und gerade richten. */
export function rectifyPage(documentId: string, page: number) {
  return sendForm(`/api/v1/documents/${documentId}/pages/${page}/rectify`, "POST");
}

export interface RectifiedPhoto {
  /** aufbereitetes Foto als JPEG - so wird es als Seite gespeichert */
  file: File;
  cropped: boolean;
  skew: number;
}

/** Foto zuschneiden, entzerren und gerade richten lassen (nur Vorschau, nichts wird gespeichert). */
export async function rectifyPhoto(photo: File, signal?: AbortSignal): Promise<RectifiedPhoto> {
  const form = new FormData();
  form.append("file", photo);
  const resp = await authFetch(`${api_base()}/api/v1/photos/rectify`, { method: "POST", body: form, signal });
  if (!resp.ok) throw new ApiError(resp.status, `Zuschnitt nicht moeglich (${resp.status})`);
  const bytes = await resp.arrayBuffer();
  const name = (photo.name || "Foto").replace(/\.[^.]+$/, "") + ".jpg";
  return {
    file: new File([bytes], name, { type: "image/jpeg" }),
    cropped: resp.headers.get("X-Cropped") === "true",
    skew: Number(resp.headers.get("X-Skew") ?? 0) || 0,
  };
}

/** Vorschaubild einer Seite (mit Anmeldung geladen). */
export async function fetchPageThumbnail(documentId: string, page: number, width = 240): Promise<Blob> {
  const resp = await authFetch(`${api_base()}/api/v1/documents/${documentId}/pages/${page}/thumbnail?width=${width}`);
  if (!resp.ok) throw new ApiError(resp.status, `Vorschau nicht verfuegbar (${resp.status})`);
  return resp.blob();
}
