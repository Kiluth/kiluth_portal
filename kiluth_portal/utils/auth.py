"""Auth: gate User creation, decide where logged-in users land.

Three responsibilities, all wired in hooks.py:

1. `restrict_signup_to_kiluth_domain` (doc_events.User.before_insert)
   — only @kiluth.com emails (and the bench Administrator) can become Users.
2. `get_user_home_page` (get_website_user_home_page)
   — every logged-in user lands on the portal page (`/welcome`) instead of
   the desk (`/app`).
3. `login_via_google` (override_whitelisted_methods)
   — wraps Frappe's Google OAuth callback. Strips stale `/desk` and `/app`
   values out of the OAuth state's `redirect_to` so they don't override
   the home-page hook above.

Why split is here, not in three files: all three override Frappe's default
identity flow for Kiluth, and they share knobs (DEFAULT_HOME_PAGE,
ALLOWED_DOMAINS). Keeping them adjacent makes the contract obvious.
"""

import base64
import json

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


_STALE_REDIRECTS = ("/desk", "/app")


def _is_stale_desk_redirect(value: str | None) -> bool:
	"""True if `value` points back at the Frappe desk and should be discarded."""
	if not value:
		return False
	target = value.lower().rstrip("/")
	return any(target.endswith(p) for p in _STALE_REDIRECTS)


@frappe.whitelist(allow_guest=True)
def login_via_google(code: str, state: str):
	"""Wrap Frappe's Google OAuth callback so logged-in users land on /welcome.

	Two problems we work around here:

	1. Stale `/desk` baked into state. When a user reaches /login from /desk
	   (saved bookmark, expired session), the login page bakes that path into
	   the OAuth state's `redirect_to`. After auth, Frappe's
	   `redirect_post_login` honors that and sends them back to the desk.

	2. Frappe's fallback when `redirect_to` is missing also goes to /desk
	   (or /apps, depending on installed apps). The `get_website_user_home_page`
	   hook is only consulted by `frappe.website.utils.get_home_page()`, which
	   is used as a *secondary* fallback in `redirect_post_login` and only for
	   non-desk users — so for our typical System User population, the hook
	   never fires. The actual `get_default_path` lives in `frappe.apps` and
	   checks installed apps + User.default_app, with no hook surface.

	Fix: force `redirect_to = DEFAULT_HOME_PAGE` into the state before the
	upstream flow runs, *unless* the user already specified a real deep link
	(e.g. /portal/foo). That way `redirect_post_login` finds a redirect_to
	value and uses it directly — no get_default_path lookup.

	Wired via `override_whitelisted_methods` in hooks.py.
	"""
	from frappe.integrations.oauth2_logins import decoder_compat
	from frappe.utils.oauth import login_via_oauth2

	try:
		decoded = json.loads(base64.b64decode(state).decode("utf-8"))
	except (ValueError, json.JSONDecodeError):
		# malformed state — let upstream handle (likely a 4xx)
		return login_via_oauth2("google", code, state, decoder=decoder_compat)

	current = decoded.get("redirect_to")
	if _is_stale_desk_redirect(current) or not current:
		decoded["redirect_to"] = DEFAULT_HOME_PAGE
		state = base64.b64encode(json.dumps(decoded).encode("utf-8")).decode("utf-8")

	return login_via_oauth2("google", code, state, decoder=decoder_compat)
