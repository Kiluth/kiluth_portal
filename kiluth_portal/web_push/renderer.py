"""Serve the service worker and web app manifest from the site root.

A service worker only controls pages under its own URL path, so it must live
at `/kiluth-push-sw.js` to cover `/app`. Frappe's StaticPage refuses `.js` and
`.json` from `www/`, and `/assets/...` would cap the scope at `/assets/`.
Hence this small `page_renderer` hook.

The manifest makes "Add to Home Screen" open the Portal as a standalone app,
which iPhone requires before it allows web push at all (iOS 16.4+).
"""

import json
import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

SW_PATH = "kiluth-push-sw.js"
MANIFEST_PATH = "kiluth-manifest.webmanifest"

MANIFEST = {
	"name": "Kiluth Portal",
	"short_name": "Kiluth",
	"start_url": "/app/todo",
	"scope": "/",
	"display": "standalone",
	"background_color": "#ffffff",
	"theme_color": "#ffffff",
	"icons": [
		{"src": "/assets/kiluth_portal/images/kiluth-icon-192.png", "sizes": "192x192", "type": "image/png"},
		{"src": "/assets/kiluth_portal/images/kiluth-icon-512.png", "sizes": "512x512", "type": "image/png"},
	],
}


class WebPushAssets(BaseRenderer):
	def can_render(self):
		return self.path in (SW_PATH, MANIFEST_PATH)

	def render(self):
		if self.path == SW_PATH:
			path = os.path.join(frappe.get_app_path("kiluth_portal"), "web_push", "service_worker.js")
			with open(path) as f:
				body = f.read()
			return Response(
				body,
				mimetype="application/javascript",
				headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
			)
		return Response(json.dumps(MANIFEST), mimetype="application/manifest+json")
