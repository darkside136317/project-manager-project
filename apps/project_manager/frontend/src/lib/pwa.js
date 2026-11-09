// Installable app: register the service worker (public/sw.js, served at /pm/sw.js) and forget what it kept when
// the user signs out, so the next person on a shared phone does not see their data offline.

export function registerServiceWorker() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator) || !window.isSecureContext) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/pm/sw.js", { scope: "/pm" }).catch(() => {
      // no worker: the app still works online
    });
  });
}

export async function clearOfflineData() {
  try {
    navigator.serviceWorker?.controller?.postMessage("pm-clear");
    if (typeof caches !== "undefined") {
      for (const key of await caches.keys()) if (key.startsWith("pm-")) await caches.delete(key);
    }
  } catch {
    // nothing kept, or not allowed: nothing to clear
  }
}
