// Kiluth Portal push service worker — served at /kiluth-push-sw.js by
// kiluth_portal/web_push/renderer.py. Shows the notification and opens the
// Task when tapped. No caching / offline logic on purpose.
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

self.addEventListener("notificationclick", (event) => {
	event.notification.close();
	const url = new URL(event.notification.data.url, self.location.origin).href;
	event.waitUntil(
		self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
			for (const w of wins) {
				if ("focus" in w) {
					w.navigate(url);
					return w.focus();
				}
			}
			return self.clients.openWindow(url);
		})
	);
});
