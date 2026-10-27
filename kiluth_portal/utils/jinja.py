"""Jinja helpers for Notification messages (hooks.py `jinja`).

`kiluth_email(...)` returns the designed Kiluth email (utils/report_email.py)
so a Notification's message can be one call:

    {{ kiluth_email(title="Expires in 30 days", kicker=doc.name,
        lines=["Renew or replace it before **" ~ doc.expiry_date ~ "**."],
        facts=[("Customer", doc.customer), ("Expiry date", doc.expiry_date)],
        hero="hero-water-wave.jpg", button="Open the resource",
        href=frappe.utils.get_url_to_form(doc.doctype, doc.name)) }}

The result starts with <!doctype>, so the Kiluth frame (templates/emails/
standard.html) adds only black around it. Values are escaped here, not in
the message.
"""


def kiluth_email(**kw):
	from frappe.utils import get_url

	from kiluth_portal.utils.report_email import email_html

	kw.setdefault("assets", get_url("/assets/kiluth_portal/"))
	kw.setdefault("portal_url", get_url())
	return email_html(**kw)
