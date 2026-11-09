// Service worker of the installable app, served at /pm/sw.js (project_manager/pwa.py replaces the build marker).
// It keeps what is needed to open the app without a connection:
//   * the app page (network first, the last good copy when offline),
//   * the built JS/CSS (cache first: their names change with every build),
//   * the app's read calls (network first, the last answer when offline) and photo thumbnails (never change).
// Writes are never cached: what is written offline waits in the outbox (IndexedDB) of the page itself.
const BUILD = "__PM_BUILD__";
const SHELL = `pm-shell-${BUILD}`;
const ASSETS = `pm-assets-${BUILD}`;
const DATA = "pm-data";
const PHOTOS = "pm-photos";
const SHELL_KEY = "/pm/__shell__";
const API = "/api/method/project_manager.project_manager.api.";
const NEVER = ["documents.download", "boot.csrf_token", "activity.search", "media.file"];

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if ((key.startsWith("pm-shell-") && key !== SHELL) || (key.startsWith("pm-assets-") && key !== ASSETS)) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data === "pm-clear") {
    event.waitUntil((async () => {
      for (const key of await caches.keys()) if (key.startsWith("pm-")) await caches.delete(key);
    })());
  }
});

async function networkFirst(request, cacheName, key = request) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok && !response.redirected) await cache.put(key, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(key);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate" && (url.pathname === "/pm" || url.pathname.startsWith("/pm/"))) {
    event.respondWith(networkFirst(request, SHELL, SHELL_KEY));
  } else if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request, ASSETS));
  } else if (url.pathname === `${API}media.file` && url.searchParams.get("size") === "thumb") {
    event.respondWith(networkFirst(request, PHOTOS));
  } else if (url.pathname.startsWith(API) && !NEVER.some((name) => url.pathname === API + name)) {
    event.respondWith(networkFirst(request, DATA));
  }
});
