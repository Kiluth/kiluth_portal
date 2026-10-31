"""Send a Web Push message to every saved device of one user.

Keys live in site_config, never in git or the DB:
  kiluth_vapid_private_key  — base64url raw P-256 private key
  kiluth_vapid_public_key   — base64url uncompressed public key (given to browsers)
  kiluth_vapid_subject      — "mailto:technology@kiluth.com"
Generate once with `vapid --gen` (py-vapid).
"""

import json

import frappe

DOCTYPE = "Web Push Subscription"
GONE = (404, 410)  # push service says this subscription no longer exists


class WebPushError(Exception):
	pass


def _vapid():
	key = frappe.conf.get("kiluth_vapid_private_key")
	if not key:
		raise WebPushError("kiluth_vapid_private_key missing from site_config")
	return key, {"sub": frappe.conf.get("kiluth_vapid_subject") or "mailto:technology@kiluth.com"}


def send_to_user(user, payload):
	"""Returns how many devices took the message. A user with no devices is 0, not an error.

	Raises WebPushError when every device failed for a reason other than "gone",
	so the outbox row goes Failed and the hourly retry tries again.
	"""
	from pywebpush import WebPushException, webpush

	subs = frappe.get_all(DOCTYPE, filters={"user": user}, fields=["name", "endpoint", "p256dh", "auth"])
	if not subs:
		return 0
	key, claims = _vapid()
	data = json.dumps(payload)
	sent, errors = 0, []
	for sub in subs:
		try:
			webpush(
				subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
				data=data,
				vapid_private_key=key,
				vapid_claims=dict(claims),
				ttl=24 * 60 * 60,
			)
			sent += 1
		except WebPushException as e:
			status = getattr(e.response, "status_code", None)
			if status in GONE:
				frappe.delete_doc(DOCTYPE, sub.name, ignore_permissions=True, force=True)
			else:
				errors.append(f"{status}: {e}")
	frappe.db.commit()
	if errors and not sent:
		raise WebPushError("; ".join(errors)[:400])
	return sent
