// Kiluth Portal push service worker — served at /kiluth-push-sw.js by
// kiluth_portal/web_push/renderer.py. Shows the notification and opens the
// Task when tapped. No offline logic on purpose: the one cache holds the tapped URL.
self.addEventListener("push", (event) => {
	let data = {};
	try {
		data = event.data ? event.data.json() : {};
	} catch (e) {
		data = { title: "Kiluth Portal", body: event.data ? event.data.text() : "" };
	}
	event.waitUntil(
		self.registration.showNotification(data.title || "Kiluth Portal", {
			body: data.body || "",
			tag: data.tag,
			data: { url: data.url || "/my-tasks" },
			icon: "/assets/kiluth_portal/images/kiluth-icon-192.png",
		})
	);
});

// A new version takes over at once: there is no cache here for an old one to keep.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// Tapping one opened the app at its home page, not at the task (Poom, 2026-11-06):
// an app this worker doesn't control can't be sent anywhere, and a phone starting
// the app from cold opens it at start_url whatever the tap asked for. So the page
// is told instead: an app that's running gets a message, and one still starting
// reads the note left here when it loads (web_push.bundle.js).
const NOTE = { cache: "kiluth-push", key: "/kiluth-push-open" };

self.addEventListener("notificationclick", (event) => {
	event.notification.close();
	const url = new URL(event.notification.data?.url || "/my-tasks", self.location.origin).href;
	event.waitUntil(open(url));
});

async function open(url) {
	const cache = await caches.open(NOTE.cache);
	await cache.put(NOTE.key, new Response(JSON.stringify({ url, at: Date.now() })));
	const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
	const win = wins.find((w) => "focus" in w);
	if (!win) return self.clients.openWindow(url);
	win.postMessage({ kiluth_open: url });
	return win.focus();
}
