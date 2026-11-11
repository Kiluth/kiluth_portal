"""Switch off ERPNext's old print formats for quotations, invoices and receipts.

The new money-doc design (Quotation Print, Invoice Print, Receipt) went live
2026-11-10 and is the default for all three. Poom (2026-11-11): once a new
design ships, nobody should be able to pick the old look from the Print menu.

These are ERPNext's standard formats, so a fixture can't own them. Frappe keeps
`disabled` when ERPNext re-imports a standard Print Format on update
(`ignore_values` in frappe/modules/import_file.py), so setting it once here
holds. Already-sent documents still open; only the menu changes.

Kept on: Sales Auditing Voucher (internal) and Sales Invoice Return (credit
notes have no new design yet).
"""

import frappe

OLD_FORMATS = [
	"Quotation Standard",
	"Quotation with Item Image",
	"Sales Invoice Print",
	"Sales Invoice Standard",
	"Sales Invoice with Item Image",
	"Bank and Cash Payment Voucher",
]


def execute():
	for name in OLD_FORMATS:
		if frappe.db.exists("Print Format", name):
			frappe.db.set_value("Print Format", name, "disabled", 1, update_modified=False)
	frappe.db.commit()
