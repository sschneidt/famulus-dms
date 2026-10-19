import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";
import { tokenStore } from "../api/client";
import { setLanguage } from "../i18n"; // Tests laufen auf Deutsch

// findBy*/waitFor warten standardmaessig nur 1 s. Auf langsamen Rechnern (GitHub Actions, NAS) reicht das nicht
// fuer das erste Rendern von Mantine in jsdom - dann waere ein Lauf zufaellig rot. Bestandene Tests warten nicht laenger.
configure({ asyncUtilTimeout: 5000 });

afterEach(async () => {
  cleanup();
  tokenStore.clear();
  await setLanguage("de", false); // ein Test hat evtl. umgeschaltet
  window.localStorage.clear();
});

// jsdom kennt diese Browser-APIs nicht, Mantine braucht sie aber.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
window.HTMLElement.prototype.scrollIntoView ??= () => undefined;

// Vorschaubilder (Blob-Adressen)
URL.createObjectURL ??= () => "blob:test";
URL.revokeObjectURL ??= () => undefined;
