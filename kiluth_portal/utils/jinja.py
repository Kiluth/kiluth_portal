"""Jinja helpers for Notification messages and print formats (hooks.py `jinja`).

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


def kiluth_money_doc(doc):
	"""Values for the quotation, invoice and receipt layout (templates/print/money_doc.html)."""
	from kiluth_portal.utils.money_docs import money_doc

	return money_doc(doc)


def kiluth_money_fonts():
	from kiluth_portal.utils.money_docs import fonts_css

	return fonts_css()


def kiluth_money_logo():
	from kiluth_portal.utils.money_docs import logo_uri

	return logo_uri()


def kiluth_thai(html):
	"""Filter: Thai runs in <span class="kt">, for wkhtmltopdf (see money_docs.thai_spans)."""
	from kiluth_portal.utils.money_docs import thai_spans

	return thai_spans(html)
