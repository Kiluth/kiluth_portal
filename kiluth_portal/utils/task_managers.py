"""Account Manager and Project Manager on a Task come from its Project.

A task that gets a project, new or moved, copies whichever of the two it has
blank (Poom, 2026-10-31). Later saves leave them alone, so changing a project's
managers doesn't rewrite its tasks, and a name someone typed stays.

Not `fetch_from` on the field, because that fills blanks on every save: every
old task would change the next time anyone touched it.

The four fields were made by hand on the live site, with no module, so the
fixtures don't carry them. `ensure_fields` adds any that are missing and never
edits one that's there, so a rebuilt site gets them and a migrate can't fail on
them, the way a fixture pointing at a missing field would.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

FIELDS = ("account_manager", "project_manager")
DEFINITIONS = {
	"Task": (("account_manager", "Account Manager", "project"), ("project_manager", "Project Manager", "account_manager")),
	"Project": (("account_manager", "Account Manager", "department"), ("project_manager", "Project Manager", "account_manager")),
}
FINISHED = ("Completed", "Cancelled")


def to_copy(task: dict, project: dict) -> dict:
	"""What a task takes from its project: only blanks, only real values."""
	return {f: project[f] for f in FIELDS if project.get(f) and not task.get(f)}


def _on_project(project: str) -> dict:
	return frappe.db.get_value("Project", project, list(FIELDS), as_dict=True) or {}


def copy_from_project(doc, method=None):
	"""Task validate hook. Runs when the task is new or its project changed."""
	if doc.project and doc.has_value_changed("project"):
		doc.update(to_copy({f: doc.get(f) for f in FIELDS}, _on_project(doc.project)))


def ensure_fields():
	"""After migrate: add any of the four fields that are missing, and make the two
	on Task quick filters. Never changes a field that already exists."""
	for doctype, fields in DEFINITIONS.items():
		for fieldname, label, after in fields:
			create_custom_field(
				doctype,
				{"fieldname": fieldname, "label": label, "fieldtype": "Link", "options": "User", "insert_after": after},
				is_system_generated=False,
			)
	for field in FIELDS:
		make_property_setter("Task", field, "in_standard_filter", 1, "Check", validate_fields_for_doctype=False)


def backfill_open_tasks(write=False):
	"""One-off, run by hand: copy into open tasks that are blank. Prints each change.

	Report only unless write is set. Writes the two fields directly, so `modified`
	doesn't move and no hook, notification or task check runs. The printed list is
	the undo: set those fields blank again.
	"""
	rows = frappe.get_all(
		"Task",
		filters=[["status", "not in", (*FINISHED, "Template")], ["project", "is", "set"]],
		fields=["name", "project", *FIELDS],
		order_by="name asc",
		limit_page_length=0,
	)
	changes = []
	for row in rows:
		values = to_copy(row, _on_project(row.project))
		if values:
			changes.append({"task": row.name, "project": row.project, **values})
			if frappe.utils.cint(write):
				frappe.db.set_value("Task", row.name, values, update_modified=False)
	if frappe.utils.cint(write):
		frappe.db.commit()
	print(frappe.as_json(changes))
	print(f"{len(changes)} of {len(rows)} open task(s) {'changed' if frappe.utils.cint(write) else 'would change'}")
	return changes
