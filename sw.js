// Avisos de Benitooo: recibe las notificaciones que manda el robot y abre la app al tocarlas.
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('push', function (e) {
  var d = {}; try { d = e.data ? e.data.json() : {}; } catch (x) { d = { title: 'Benitooo', body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Benitooo', { body: d.body || '', icon: 'foto-192.png', badge: 'foto-192.png', tag: d.tag || undefined, data: { url: d.url || './' } }));
});
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || './';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (L) {
    for (var i = 0; i < L.length; i++) { if ('focus' in L[i]) { L[i].postMessage('refrescar'); return L[i].focus(); } }
    return self.clients.openWindow(url);
  }));
});
