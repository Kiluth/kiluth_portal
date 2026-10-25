"""Stop duplicate customers (doc_events.Customer.before_insert).

A name that matches an existing customer once tidied (customer_rules.py) is
refused with a link to the one we have. A Portal admin (System Manager) can
still create it, for the rare client whose name really does overlap.
"""

import frappe

from kiluth_portal.utils.customer_rules import similar_customer


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
