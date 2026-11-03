"""Task change history on a LOCAL THROWAWAY bench. Creates a made-up task and deletes it.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_history.run

Every way a task is changed must leave a record of who changed what, and when.
"""

import json

import frappe
from frappe.desk.doctype.kanban_board.kanban_board import update_order_for_single_card
from frappe.desk.form.assign_to import add as assign

from kiluth_portal.utils import task_page

REQUESTER, DOER, ADMIN = "e2e-sales@kiluth.com", "e2e-member@kiluth.com", "e2e-assigner@kiluth.com"


def _as(user, fn):
	frappe.set_user(user)
	try:
		return fn()
	finally:
		frappe.set_user("Administrator")


def _changes(task):
	"""[(who, field, old, new)] from the task's Version rows, oldest first."""
	out = []
	for v in frappe.get_all("Version", filters={"ref_doctype": "Task", "docname": task},
	                        fields=["owner", "data"], order_by="creation asc"):
		for field, old, new in json.loads(v.data).get("changed") or []:
			out.append((v.owner, field, old, new))
	return out


def _has(task, who, field, new):
	# Dates come back as datetimes ("2026-12-01 00:00:00").
	return any(w == who and f == field and str(n).startswith(str(new)) for w, f, _, n in _changes(task))


def run():
	frappe.set_user("Administrator")
	out = []
	t = _as(REQUESTER, lambda: frappe.get_doc({"doctype": "Task", "subject": "E2E history", "status": "Open"})
	        .insert(ignore_permissions=True).name)
	try:
		out.append(("Task tracks changes", bool(frappe.get_meta("Task").track_changes), None))

		def form_save():
			doc = frappe.get_doc("Task", t)
			doc.description = "<p>Done when the history shows this.</p>"
			doc.exp_end_date = "2026-12-01"
			doc.save()
		_as(REQUESTER, form_save)
		out.append(("form save: description, with who", _has(t, REQUESTER, "description", "<p>Done when the history shows this.</p>"), _changes(t)))
		out.append(("form save: due date, with who", _has(t, REQUESTER, "exp_end_date", "2026-12-01"), _changes(t)))

		_as(DOER, lambda: frappe.client.set_value("Task", t, "status", "Working"))
		out.append(("phone sheet (set_value): status, with who", _has(t, DOER, "status", "Working"), _changes(t)))

		_as(DOER, lambda: update_order_for_single_card("Tasks", t, "Working", "Pending Review", 0, 0))
		out.append(("board move: status, with who", _has(t, DOER, "status", "Pending Review"), _changes(t)))

		modified = str(frappe.db.get_value("Task", t, "modified"))
		_as(REQUESTER, lambda: frappe.client.set_value("Task", t, "status", "Working"))
		modified = str(frappe.db.get_value("Task", t, "modified"))
		_as(DOER, lambda: task_page.set_field(t, "exp_end_date", "2026-12-15", modified))
		out.append(("task page edit: due date, with who", _has(t, DOER, "exp_end_date", "2026-12-15"), _changes(t)))

		_as(ADMIN, lambda: assign({"doctype": "Task", "name": t, "assign_to": [DOER]}))
		_as(ADMIN, lambda: task_page.hand_over(t, REQUESTER))
		said = frappe.get_all("Comment", filters={"reference_doctype": "Task", "reference_name": t,
		                                          "comment_type": ["in", ["Assigned", "Assignment Completed"]]},
		                      fields=["owner", "comment_type", "content"], order_by="creation asc")
		out.append(("assignee changes: who and when are in the task's activity",
		            [c.owner for c in said] == [ADMIN] * len(said) and len(said) >= 2, said))

		v = frappe.get_all("Version", filters={"ref_doctype": "Task", "docname": t}, fields=["creation"], limit=1)
		out.append(("each change carries its time", bool(v and v[0].creation), v))
	finally:
		frappe.db.delete("Version", {"ref_doctype": "Task", "docname": t})
		frappe.db.delete("Comment", {"reference_doctype": "Task", "reference_name": t})
		frappe.db.delete("ToDo", {"reference_type": "Task", "reference_name": t})
		frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(ok for _, ok, _ in out)}/{len(out)}")
