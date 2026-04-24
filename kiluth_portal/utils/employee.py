"""Cross-doctype: autofill `employee` from the logged-in user.

Wired via `doc_events` in hooks.py for Expense Claim, Leave Application, and
Timesheet — replaces 3 separate Server Scripts in the legacy prod instance.
"""

import frappe


def autofill_employee(doc, method=None):
	if doc.get("employee"):
		return

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if employee:
		doc.employee = employee
