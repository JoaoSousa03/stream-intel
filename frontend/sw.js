// sw.js — Stream Intelligence Service Worker
// Strategy:
//   - Static assets (CSS, JS, fonts, icons) → Cache First
//   - API calls (/api/*)                     → Network First (never cache)
//   - HTML pages                             → Network First, fall back to cached shell
//   - Web Push notifications                 → showNotification on push event

const CACHE_NAME = 'streamintel-v13';

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  '/',
  '/css/app.css',
  '/js/api.js',
  '/js/auth.js',
  '/js/catalog.js',
  '/js/library.js',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
];

// ── Install: pre-cache static shell ─────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting(); // activate immediately
});

// ── Activate: delete old caches ──────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim(); // take control of all open tabs immediately
});

// ── Fetch: routing logic ─────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Never intercept browser navigations (mode:'navigate') — let them go straight
  // to the network. This is critical for OAuth callbacks: when Google redirects
  // the browser to /api/auth/google-callback, the SW must not touch it because
  // fetch() cannot proxy navigation requests and throws TypeError: Failed to fetch.
  if (request.mode === 'navigate') return;

  // API calls → always go to network (never serve stale data)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Static assets (CSS, JS, images) → network-first so updates are always served;
  // fall back to cache when offline
  if (
    url.pathname.startsWith('/css/') ||
    url.pathname.startsWith('/js/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname.match(/\.(png|svg|jpg|jpeg|webp|woff2?|ttf)$/)
  ) {
    event.respondWith(
      fetch(request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return resp;
      }).catch(() => caches.match(request))
    );
    return;
  }

  // HTML / navigation → network-first, fall back to cached index
  event.respondWith(
    fetch(request)
      .then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return resp;
      })
      .catch(() => caches.match('/') ) // offline: serve the app shell
  );
});

// ── Web Push ─────────────────────────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) {}

  const title = data.title || 'StreamIntel';
  const body  = data.body  || 'You have a new notification.';

  e.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon:     '/icons/icon-192.png',
      badge:    '/icons/icon-192.png',
      vibrate:  [100, 50, 100],
      data:     { url: data.url || '/' },
      tag:      'streamintel-notif',
      renotify: true,
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const rel    = (e.notification.data && e.notification.data.url) || '/';
  // Must be an absolute URL — Chrome on Android uses it to decide whether to
  // open the installed PWA (standalone) or a new browser tab. A relative path
  // is mis-handled and always opens in the browser.
  const target = rel.startsWith('http') ? rel : (self.location.origin + rel);

  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      // Reuse an existing app window: navigate it to the target URL, then focus.
      // WindowClient.navigate() is the right API here — c.focus() alone does not
      // change the current page.
      const existing = list.find(c => c.url.startsWith(self.location.origin));
      if (existing) {
        const p = ('navigate' in existing)
          ? existing.navigate(target).then(wc => wc && wc.focus())
          : Promise.resolve(existing.focus());
        return p;
      }
      // No existing window — open a new one. On Android Chrome, openWindow with
      // an in-scope absolute URL opens inside the installed PWA, not the browser.
      return clients.openWindow(target);
    })
  );
});
