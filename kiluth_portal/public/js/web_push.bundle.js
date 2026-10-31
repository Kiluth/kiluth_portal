// Phone notifications for Kiluth Tasks (loaded via hooks.py -> app_include_js).
// "Phone notifications" in the user menu (a Navbar Settings item added by
// web_push/menu.py on migrate) calls kiluth_enable_push(). Tapping it asks the
// browser for permission (must come from a tap, iPhone insists) and saves the
// subscription server-side. On iPhone this only works after "Add to Home
// Screen" and opening the Portal from that icon.
(function () {
	const SW_URL = "/kiluth-push-sw.js";
	const API = "kiluth_portal.web_push.api";

	// iPhone reads these at "Add to Home Screen": the manifest makes the icon
	// open standalone (needed for push), apple-touch-icon is the icon itself.
	function addHeadLinks() {
		const links = [
			["manifest", "/kiluth-manifest.webmanifest"],
			["apple-touch-icon", "/assets/kiluth_portal/images/kiluth-icon-192.png"],
		];
		for (const [rel, href] of links) {
			if (document.querySelector(`link[rel="${rel}"]`)) continue;
			const link = document.createElement("link");
			link.rel = rel;
			link.href = href;
			document.head.appendChild(link);
		}
	}

	function urlBase64ToUint8Array(base64) {
		const padding = "=".repeat((4 - (base64.length % 4)) % 4);
		const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
		return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
	}

	function supported() {
		return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
	}

	async function enable() {
		if (!supported()) {
			const ios = /iPhone|iPad/.test(navigator.userAgent);
			frappe.msgprint(
				ios
					? __("On iPhone: tap Share, then Add to Home Screen. Open the Portal from that icon and try again.")
					: __("This browser can't receive notifications.")
			);
			return;
		}
		const permission = await Notification.requestPermission();
		if (permission !== "granted") {
			frappe.msgprint(__("Notifications are blocked. Allow them in your browser settings."));
			return;
		}
		const reg = await navigator.serviceWorker.register(SW_URL, { scope: "/" });
		await navigator.serviceWorker.ready;
		const key = (await frappe.call(`${API}.get_vapid_public_key`)).message;
		const sub =
			(await reg.pushManager.getSubscription()) ||
			(await reg.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey: urlBase64ToUint8Array(key),
			}));
		const json = sub.toJSON();
		await frappe.call(`${API}.subscribe`, {
			endpoint: json.endpoint,
			p256dh: json.keys.p256dh,
			auth: json.keys.auth,
			user_agent: navigator.userAgent,
		});
		await frappe.call(`${API}.send_test`);
		frappe.show_alert({ message: __("Phone notifications are on"), indicator: "green" });
	}

	addHeadLinks();
	window.kiluth_enable_push = () => {
		enable().catch((err) => frappe.msgprint(String(err)));
		return false;
	};
})();
