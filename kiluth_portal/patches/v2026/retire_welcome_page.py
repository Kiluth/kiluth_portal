"""Delete the `/welcome` tile page (Web Page "portal").

People land on their Task list now (TASK-2026-00083, utils/home.py). Fixtures
never delete records, so the old page would stay published without this.
`/welcome` itself redirects to `/my-tasks` (hooks.py website_redirects).
"""

import frappe


def execute():
	if frappe.db.exists("Web Page", "portal"):
		frappe.delete_doc("Web Page", "portal", ignore_permissions=True)
