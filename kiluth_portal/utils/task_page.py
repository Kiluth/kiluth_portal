"""What the Task page needs beyond the Task itself: its chain, hand-over and edits.

A dependency is stored only on the task that waits, so "what this blocks" takes a
query. Hand-over replaces the assignee, never adds one: a task has one owner.

Some titles are load-bearing: jobs find their tasks by title, so renaming one means
a duplicate task or a job that never runs. set_field won't touch those.
"""

from __future__ import annotations

import frappe

from kiluth_portal.api.client_brief import SUBJECT as BRIEF_PREFIX
from kiluth_portal.utils.close_report import SUBJECT_PREFIX as CLOSE_PREFIX
from kiluth_portal.utils.lead_routing import SUBJECT_PREFIX as LEAD_PREFIX, move

FIXED_PREFIXES = (CLOSE_PREFIX, LEAD_PREFIX, BRIEF_PREFIX)
SYSTEM_OWNERS = ("Administrator", "Guest")  # the scheduler's tax, year-end and VAT tasks
EDITABLE = ("subject", "priority", "exp_end_date", "project", "description")
FINISHED = ("Completed", "Cancelled")


def title_is_fixed(subject: str, owner: str) -> bool:
	return subject.startswith(FIXED_PREFIXES) or owner in SYSTEM_OWNERS


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
	return {
		"waits_on": _rows([d.task for d in doc.depends_on]),
		"blocks": _rows(blocks),
		"project": project,
		"title_fixed": title_is_fixed(doc.subject, doc.owner),
	}


@frappe.whitelist(methods=["POST"])
def set_field(task: str, field: str, value: str | None = None, modified: str | None = None) -> str:
	"""Change one field from the Task page. Returns the task's new `modified`.

	`modified` is what the page last loaded: a page left open can't overwrite a
	change made since, by a person or a job.
	"""
	if field not in EDITABLE:
		frappe.throw(frappe._("That field can't be changed here"))
	doc = frappe.get_doc("Task", task)
	doc.check_permission("write")
	if doc.status in FINISHED:
		frappe.throw(frappe._("This task is finished. Change it under All details."))
	if str(doc.modified) != modified:
		frappe.throw(frappe._("This task changed while you had it open. Check it, then try again."))
	if field == "subject":
		value = (value or "").strip()
		if not value:
			frappe.throw(frappe._("A task needs a title"))
		if title_is_fixed(doc.subject, doc.owner) or value.startswith(FIXED_PREFIXES):
			frappe.throw(frappe._("Jobs find this task by its title, so it can't be renamed."))
	doc.set(field, value or None)
	doc.save()
	return str(doc.modified)


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
