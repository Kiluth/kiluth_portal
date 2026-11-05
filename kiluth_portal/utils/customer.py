"""Rules on a customer's name (doc_events.Customer).

A name that matches an existing customer once tidied (customer_rules.py) is
refused with a link to the one we have. A Portal admin (System Manager) can
still create it, for the rare client whose name really does overlap.

A name must be in English, for everyone. Existing customers with a Thai name
still save as long as the name isn't changed.
"""

import frappe

from kiluth_portal.utils.customer_rules import not_english, similar_customer


def block_duplicate(doc, method=None):
	if "System Manager" in frappe.get_roles():
		return
	rows = frappe.get_all("Customer", fields=["name", "customer_name"])
	names = {r.name: r.name for r in rows} | {r.customer_name: r.name for r in rows if r.customer_name}
	hit = similar_customer(doc.customer_name or doc.name, list(names))
	if hit:
		existing = names[hit]
		link = frappe.utils.get_url_to_form("Customer", existing)
		frappe.throw(
			f'A client like this already exists: <a href="{link}">{frappe.utils.escape_html(existing)}</a>. '
			"Use that one. Need the Thai or registered name on documents? Put it in that client's "
			"Legal name (for documents). If this really is a different client, ask a Portal admin to create it.",
			title="Client already exists",
		)


def english_name(doc, method=None):
	"""Validate: a new customer's name and ID, or a changed name, must be English."""
	if doc.is_new():
		names = [doc.customer_name, doc.name]
	elif doc.has_value_changed("customer_name"):
		names = [doc.customer_name]
	else:
		return
	# Whole words, not characters: a Thai vowel mark shown on its own is unreadable.
	bad = list(dict.fromkeys(w for n in names for w in (n or "").split() if not_english(w)))
	if bad:
		frappe.throw(
			"Use the English company name as the client name. Put the Thai or registered name in "
			"Legal name (for documents): quotations, invoices and receipts print that one. "
			f"Not English: {frappe.utils.escape_html(' '.join(bad[:3]))}",
			title="Client name must be in English",
		)
