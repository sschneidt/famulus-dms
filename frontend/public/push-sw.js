/* Push-Benachrichtigungen von Famulus DMS anzeigen (wird vom Service Worker per importScripts geladen,
   siehe vite.config.ts). Inhalt: {title, body, url, tag} - verschluesselt vom Server
   (backend/homedms/core/webpush.py). */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Famulus DMS", {
      body: data.body || "",
      tag: data.tag || "homedms",
      renotify: true,
      lang: "de",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin)) {
          try {
            await client.navigate(url);
          } catch {
            /* nicht kontrolliertes Fenster: nur nach vorn holen */
          }
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
