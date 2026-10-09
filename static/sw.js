self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open('poker-store').then((cache) => cache.addAll([
      '/',
      '/player',
      '/static/css/style.css',
      '/static/img/rankings.png'
    ])),
  );
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then((response) => response || fetch(e.request)),
  );
});
