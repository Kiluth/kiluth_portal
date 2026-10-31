"""What the Task page needs beyond the Task itself: its chain, and hand-over.

A dependency is stored only on the task that waits, so "what this blocks" takes a
query. Hand-over replaces the assignee, never adds one: a task has one owner.
"""

from __future__ import annotations

import frappe

from kiluth_portal.utils.lead_routing import move


def _rows(names: list[str]) -> list[dict]:
	# get_list keeps Task permissions: a task this user can't read just isn't listed.
	if not names:
		return []
	return frappe.get_list(
		"Task",
		filters={"name": ["in", names]},
		fields=["name", "subject", "status"],
		order_by="name asc",
	)


@frappe.whitelist()
def links(task: str) -> dict:
	doc = frappe.get_doc("Task", task)
	doc.check_permission("read")
	blocks = frappe.get_all(
		"Task Depends On", filters={"parenttype": "Task", "task": task}, pluck="parent", distinct=True
	)
	project = frappe.db.get_value("Project", doc.project, "project_name") if doc.project else None
	return {"waits_on": _rows([d.task for d in doc.depends_on]), "blocks": _rows(blocks), "project": project}


@frappe.whitelist(methods=["POST"])
def hand_over(task: str, to_user: str) -> str:
	"""Make `to_user` the task's one assignee."""
	doc = frappe.get_doc("Task", task)
	doc.check_permission("write")
	if not frappe.db.get_value("User", to_user, "enabled"):
		frappe.throw(frappe._("{0} is not an active user").format(to_user))
	current = frappe.get_all(
		"ToDo", filters={"reference_type": "Task", "reference_name": task, "status": "Open"}, pluck="allocated_to"
	)
	if current != [to_user]:
		move(task, doc.subject, to_user)
	return to_user
