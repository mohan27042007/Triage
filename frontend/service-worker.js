/* Triage only receives privacy-preserving reminder summaries via Web Push. */
self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = {};
  }
  event.waitUntil(self.registration.showNotification(payload.title || "Triage deadline reminder", {
    body: payload.body || "Open Triage to review your due-soon obligations.",
    icon: "/assets/triage-pulse.png",
    badge: "/assets/triage-pulse.png",
    data: { url: payload.url || self.location.origin },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || self.location.origin;
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => client.url.startsWith(self.location.origin));
    return existing ? existing.focus() : clients.openWindow(targetUrl);
  }));
});
