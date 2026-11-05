"""No VAT rows on quotations, sales orders and invoices (doc_events validate).

Kiluth isn't VAT-registered, so a taxes row on a VAT account is refused when a
draft is saved or submitted (vat_rules.py). Returns and credit notes are left
alone: they reverse an invoice that already charged it. Submitted and cancelled
documents still open, print and cancel.
"""

import frappe

from kiluth_portal.utils.vat_rules import VAT_ACCOUNT_NAME, needs_check, vat_rows


def no_vat_rows(doc, method=None):
	"""Validate: refuse a draft whose taxes table has a row on a VAT account."""
	if doc.get("is_return") or not needs_check(doc.docstatus, getattr(doc, "_action", None)):
		return
	if not doc.get("taxes"):
		return
	accounts = frappe.get_all("Account", filters={"account_name": VAT_ACCOUNT_NAME, "is_group": 0}, pluck="name")
	if vat_rows(doc.taxes, accounts):
		frappe.throw("Kiluth is not VAT-registered. Remove the VAT row.", title="No VAT on Kiluth documents")
