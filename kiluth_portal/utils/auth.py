"""Auth: gate User creation, decide where logged-in users land.

Two responsibilities, both wired in hooks.py:

1. `restrict_signup_to_kiluth_domain` (doc_events.User.before_insert)
   — only @kiluth.com emails (and the bench Administrator) can become Users.
2. `get_user_home_page` (get_website_user_home_page)
   — every logged-in user lands on the portal page (`/welcome`) instead of
   the desk (`/app`).

Why split is here, not in two files: both override Frappe's default identity
flow for Kiluth, and either change touches the other (the signup gate decides
who *gets* a User; the redirect decides where they go next). Keeping them
adjacent makes the contract obvious to the next person who reads it.
"""

import frappe

ALLOWED_DOMAINS = ("@kiluth.com",)
DEFAULT_HOME_PAGE = "/welcome"


def restrict_signup_to_kiluth_domain(doc, method=None):
	"""Block User creation for non-Kiluth emails.

	With Google SSO on and `disable_signup=0` in Website Settings, any
	successful Google login that doesn't match an existing User would create
	one. We want that for Kiluth staff (HR doesn't pre-create every new hire's
	User record) but bounce everyone else.

	- User.email ends with `@kiluth.com`, or is Administrator/Guest → allowed.
	- Anything else → frappe.throw, which surfaces as a "Not Allowed" page
	  during the OAuth callback. The Google session is established but no
	  Frappe User gets created.

	ALLOWED_DOMAINS is a tuple so we can append (e.g. an acquired company's
	domain) without rewriting the predicate.
	"""
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


def get_user_home_page(user):
	"""Land logged-in users on the Kiluth portal page, not the desk.

	Frappe's default `redirect_post_login` sends desk users to `/app`. We want
	`/welcome` (the Web Page named "portal", route "welcome") to be the
	universal landing — that's where Kiluth's tile-grid menu lives, and it's
	the right starting point for both staff and any future portal-only roles.

	Frappe calls `get_website_user_home_page` hooks in
	`frappe.utils.oauth.get_default_path` *before* falling back to
	`/app/<default_app>` or `/app`. Returning a path here wins over both.

	`user` is the user_id (email). Currently we return the same path for
	everyone; the parameter is here so a future change can route, say,
	"Finance" users straight to a finance dashboard.
	"""
	return DEFAULT_HOME_PAGE
