"""Auth: gate User creation to the kiluth.com domain.

Wired via `doc_events.User.before_insert` in hooks.py.

Why: with Google SSO turned on and `disable_signup=0` in Website Settings,
any successful Google login that doesn't match an existing User would create
one. We want to allow that for Kiluth staff (so HR doesn't have to pre-create
each new hire's User record), but bounce anyone else.

Behavior:
- User.email ends with `@kiluth.com` (or is the bench Administrator) → allowed.
- Anything else → frappe.throw, which surfaces as a 403 web page during the
  OAuth callback. The Google session is established but no Frappe User gets
  created, and the visitor lands on a "Not Allowed" page.

Constants:
- ALLOWED_DOMAINS: lowercase, with leading "@" — easy to extend later if
  Kiluth picks up another domain (e.g. an acquired company).
"""

import frappe

ALLOWED_DOMAINS = ("@kiluth.com",)


def restrict_signup_to_kiluth_domain(doc, method=None):
	# Bench-managed system users — never block these.
	if doc.name in ("Administrator", "Guest"):
		return

	email = (doc.email or "").lower().strip()
	if not email:
		# Frappe's own validation will catch the missing-email case; let it.
		return

	if email.endswith(ALLOWED_DOMAINS):
		return

	frappe.throw(
		frappe._(
			"Sign-up is restricted to Kiluth staff. "
			"Please use your @kiluth.com Google account, or ask an administrator to invite you."
		),
		title=frappe._("Not Allowed"),
	)
