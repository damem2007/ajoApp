// Installable mobile web shell. Financial and identity data are never cached offline.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
