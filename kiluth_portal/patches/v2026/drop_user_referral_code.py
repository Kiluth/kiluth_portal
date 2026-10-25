"""Remove the User "Referral code" field added on 2026-10-25.

Planner links now use the Portal username instead (Poom, 2026-10-25), so the
field was never filled in. Deleting the Custom Field also drops its column.
"""

import frappe


def execute():
	name = "User-kiluth_referral_code"
	if frappe.db.exists("Custom Field", name):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True)
