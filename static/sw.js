/* EYO client portal — service worker.
 *
 * Deliberately conservative: the portal is token-gated and money-sensitive, so
 * we NEVER serve a stale authed page as if it were live. Strategy:
 *   - navigations (HTML): network-first, fall back to a cached offline shell
 *     only when truly offline. We do not cache /portal/<token> responses.
 *   - static assets (icons/manifest): cache-first (stale-while-revalidate).
 * Bump CACHE when the offline shell changes to retire old caches.
 */
const CACHE = "eyo-portal-v1";
const OFFLINE_URL = "/app?offline=1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll([
      "/app",
      "/static/icons/icon-192.png",
      "/static/icons/icon-512.png",
      "/static/manifest.webmanifest",
    ])).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Navigations: always try the network first so authed/token pages stay fresh.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL).then((r) => r || caches.match("/app")))
    );
    return;
  }

  // Static assets only: stale-while-revalidate.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const network = fetch(req).then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        }).catch(() => cached);
        return cached || network;
      })
    );
  }
});
