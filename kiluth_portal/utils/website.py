"""Idempotent Website Settings wiring.

Runs on every `bench migrate` to make sure key website defaults match what the
rest of the portal stack expects (e.g. home_page points at /welcome so users
hitting `/` land on the Kiluth Portal tile page, not ERPNext's stock account
view).

Safe to re-run — each setting is only written if the current value differs.
"""

import frappe


# Branding assets ship with the app itself (see kiluth_portal/public/images/),
# so references point at `/assets/kiluth_portal/images/*` rather than the
# site-local `/files/*` directory. That way a fresh `bench migrate` on an empty
# site still wires up the Kiluth logo without any out-of-band file copy.
LOGO_URL = "/assets/kiluth_portal/images/logo-gray.png"
FAVICON_URL = "/assets/kiluth_portal/images/favicon.ico"

DESIRED_WEBSITE_SETTINGS = {
	"home_page": "/welcome",
	"app_name": "Kiluth Portal",
	"app_logo": LOGO_URL,
	"banner_image": LOGO_URL,  # load-bearing for the portal/web navbar
	"favicon": FAVICON_URL,
}

DESIRED_NAVBAR_SETTINGS = {
	"app_logo": LOGO_URL,
}


def _apply_settings(doctype: str, desired: dict):
	doc = frappe.get_doc(doctype, doctype)
	changed = False
	for field, wanted in desired.items():
		current = doc.get(field)
		if current == wanted:
			continue
		doc.set(field, wanted)
		changed = True
		print(f"[kiluth_portal] {doctype}.{field}: {current!r} -> {wanted!r}")
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()


def apply_website_settings():
	_apply_settings("Website Settings", DESIRED_WEBSITE_SETTINGS)
	_apply_settings("Navbar Settings", DESIRED_NAVBAR_SETTINGS)
