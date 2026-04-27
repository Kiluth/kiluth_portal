"""Daily scheduler tasks. Port of prod's `Resource Status Daily Recalculation`.

Re-runs the Resource status calculation on every non-archived/deleted Resource
so the 30/15/5/3/1-day expiry notifications can fire on time without waiting
for someone to manually save each record.

Resource.before_save already performs the same calc for single-record saves
(see kiluth_hosting/doctype/resource/resource.py); this is just the daily
bulk version.
"""

import frappe
from frappe.utils import today

from kiluth_portal.kiluth_hosting.doctype.resource.resource import compute_resource_status


def recalc_resource_status():
	resources = frappe.get_all(
		"Resource",
		filters={"status": ["not in", ["Archived", "Deleted"]]},
		fields=["name", "created_date", "expiry_date", "status"],
	)
	today_str = today()
	updated = 0

	for r in resources:
		new_status = compute_resource_status(r.created_date, r.expiry_date, today_str)

		if new_status != r.status:
			frappe.db.set_value(
				"Resource", r.name, "status", new_status, update_modified=False
			)
			updated += 1

	if updated:
		frappe.db.commit()
