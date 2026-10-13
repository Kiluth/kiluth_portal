"""Send a Web Push message to every saved device of each user.

Keys live in site_config, never in git or the DB:
  kiluth_vapid_private_key  — base64url raw P-256 private key
  kiluth_vapid_public_key   — base64url uncompressed public key (given to browsers)
  kiluth_vapid_subject      — "mailto:technology@kiluth.com"
Generate once with `vapid --gen` (py-vapid) or the snippet in SUMMARY.md.
"""

import json

import frappe

GONE = (404, 410)  # push service says this subscription no longer exists


def _vapid():
	conf = frappe.conf
	key = conf.get("kiluth_vapid_private_key")
	if not key:
		frappe.log_error("kiluth_vapid_private_key missing from site_config", "Web Push")
		return None, None
	return key, {"sub": conf.get("kiluth_vapid_subject") or "mailto:technology@kiluth.com"}


def send_to_users(users, payload):
	from pywebpush import WebPushException, webpush

	key, claims = _vapid()
	if not key:
		return
	subs = frappe.get_all(
		"Web Push Subscription",
		filters={"user": ["in", users]},
		fields=["name", "endpoint", "p256dh", "auth"],
	)
	data = json.dumps(payload)
	for sub in subs:
		try:
			webpush(
				subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
				data=data,
				vapid_private_key=key,
				vapid_claims=dict(claims),
				ttl=24 * 60 * 60,
			)
		except WebPushException as e:
			status = getattr(e.response, "status_code", None)
			if status in GONE:
				frappe.delete_doc("Web Push Subscription", sub.name, ignore_permissions=True, force=True)
			else:
				frappe.log_error(f"{status}: {e}", "Web Push")
	frappe.db.commit()
