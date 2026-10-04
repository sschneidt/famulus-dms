/**
 * Web-Push im Browser: Berechtigung holen, beim Push-Dienst des Browsers anmelden.
 * Die eigentliche Anzeige uebernimmt der Service Worker (public/push-sw.js).
 */

export type PushSupport = "supported" | "insecure" | "ios-needs-install" | "unsupported";

function isIos(): boolean {
  return (
    /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function pushSupport(): PushSupport {
  if (!window.isSecureContext) return "insecure";
  const available = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (isIos() && !isStandalone()) return "ios-needs-install";
  return available ? "supported" : "unsupported";
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const base64 = (value + "=".repeat((4 - (value.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function sameKey(current: ArrayBuffer | null | undefined, expected: Uint8Array): boolean {
  if (!current) return false;
  const a = new Uint8Array(current);
  return a.length === expected.length && a.every((v, i) => v === expected[i]);
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(
      () => reject(new Error("Der Hintergrunddienst der App läuft nicht – bitte die Seite neu laden.")),
      10_000,
    ),
  );
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

/** Push-Adresse dieses Geraets, falls schon angemeldet. */
export async function currentEndpoint(): Promise<string | null> {
  if (pushSupport() !== "supported") return null;
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  return sub?.endpoint ?? null;
}

export interface BrowserSubscription {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export async function subscribePush(publicKey: string): Promise<BrowserSubscription> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error(
      permission === "denied"
        ? "Benachrichtigungen sind für HomeDMS blockiert – in den Website-Einstellungen des Browsers erlauben."
        : "Benachrichtigungen wurden nicht erlaubt.",
    );
  }
  const reg = await registration();
  const key = base64UrlToBytes(publicKey);
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub.options.applicationServerKey, key)) {
    await sub.unsubscribe(); // anderer Server/Schluessel: neu anmelden
    sub = null;
  }
  sub ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const json = sub.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth)
    throw new Error("Der Browser hat keine Push-Adresse geliefert.");
  return { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } };
}

/** Dieses Geraet beim Push-Dienst abmelden (der Server vergisst es separat). */
export async function unsubscribePush(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  await sub?.unsubscribe();
}
