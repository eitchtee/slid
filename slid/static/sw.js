// Served from /sw.js so it controls the whole site.
// Pages and boards: network first, falling back to cache (days you've opened work offline).
// Our static files: served from cache while refreshing in the background.
// CDN files are pinned to exact versions, so they're cached once and reused.
const CACHE = "slid-v7";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) event.respondWith(cacheFirst(req));
  else if (url.pathname.startsWith("/static/")) event.respondWith(staleWhileRevalidate(event, req));
  else event.respondWith(networkFirst(req));
});

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
  return res;
}

async function staleWhileRevalidate(event, req) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(req);
  const fresh = fetch(req).then((res) => {
    if (res.ok) cache.put(req, res.clone());
    return res;
  });
  if (cached) {
    event.waitUntil(fresh.catch(() => {}));
    return cached;
  }
  return fresh;
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    // Every page is the same shell (the client routes by path), so any cached page will do.
    const cached = (await cache.match(req)) ?? (req.mode === "navigate" && (await cache.match("/")));
    if (cached) return cached;
    throw err;
  }
}
