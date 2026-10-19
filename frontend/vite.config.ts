/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Backend fuer die Entwicklung (npm run dev): Vite leitet /api und /health dorthin weiter.
// Im Betrieb liefert das Backend die gebauten Dateien selbst aus (gleicher Ursprung, kein Proxy).
const backend = process.env.HOMEDMS_BACKEND ?? "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "Famulus DMS",
        short_name: "Famulus DMS",
        description: "Dokumentenverwaltung für den Haushalt",
        lang: "de",
        start_url: "/",
        display: "standalone",
        theme_color: "#1c7ed6",
        background_color: "#ffffff",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Nur die App selbst wird offline vorgehalten - API-Antworten und Dokumente nie
        // (sie sollen immer aktuell sein und nicht unbemerkt auf dem Geraet liegen bleiben).
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/redoc/, /^\/openapi\.json/, /^\/health/],
        // Push-Benachrichtigungen anzeigen und beim Antippen die App oeffnen (public/push-sw.js)
        importScripts: ["push-sw.js"],
      },
    }),
  ],
  build: {
    // Eine einzige Datei (~270 KB gzip) ist fuer die Nutzung im Heimnetz unkritisch
    chunkSizeWarningLimit: 1200,
  },
  server: {
    proxy: {
      "/api": backend,
      "/health": backend,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    testTimeout: 30000, // Standard 5 s: zu knapp fuer langsame Rechner (siehe src/test/setup.ts)
    hookTimeout: 30000,
  },
});
