"""A Task's Customer is its project's customer, so the Task list can filter by client.

Poom asked for it on 2026-11-05. The field is read only and always says what the
project says: `fetch_from` refills it on every task save, and `follow_project`
rewrites a project's tasks when the project's customer changes, because
fetch_from never looks back from the project. A task with no project has none.

Made here and not in the fixtures so `ensure_field` can fill the column in the
same step that creates it: patches run before fixtures, so a patch would find no
column to fill.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

# Every task whose customer isn't its project's. NULL-safe, so a task with no
# project and a blank customer matches nothing.
_TASKS = "`tabTask` t left join `tabProject` p on p.name = t.project"
_DIFFERENT = "not (t.customer <=> p.customer)"


def ensure_field():
	"""After migrate: add the field if it's missing, then line every task up with
	its project. Never edits a field that's already there."""
	create_custom_field(
		"Task",
		{
			"fieldname": "customer",
			"label": "Customer",
			"fieldtype": "Link",
			"options": "Customer",
			"insert_after": "project",
			"fetch_from": "project.customer",
			"read_only": 1,
			"in_standard_filter": 1,
			"in_list_view": 1,
		},
		is_system_generated=False,
	)
	sync_all()


def sync_all():
	"""Set each task's customer to its project's. Writes the column directly, so
	`modified` doesn't move and no hook, notification or task check runs.
	Returns how many tasks changed."""
	changed = frappe.db.sql(f"select count(*) from {_TASKS} where {_DIFFERENT}")[0][0]
	if changed:
		frappe.db.sql(f"update {_TASKS} set t.customer = p.customer where {_DIFFERENT}")
	return changed


def follow_project(doc, method=None):
	"""Project on_update: its tasks take the project's new customer, quietly."""
	if doc.has_value_changed("customer"):
		frappe.db.set_value("Task", {"project": doc.name}, "customer", doc.customer, update_modified=False)
