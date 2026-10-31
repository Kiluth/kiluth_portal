"""Keep the name on a completed Task.

ERPNext's Task closes every assignment when a task is completed, and again on
every later save of a completed task (`validate_status` and `unassign_todo` in
erpnext/projects/doctype/task/task.py). Kiluth's Task Usage Guideline needs the
opposite: a finished task keeps its holder, the person who did the work, so
anyone can see who to ask about that area later ("How a Task Moves").

So completed tasks keep their assignees. A cancelled task carries its
requester instead: nothing was delivered, so the person who asked for it is the
one to ask about it (docs.kiluth.com/delivery/working-with-tasks). The requester
is the task's creator; tasks the system created keep whoever is assigned.

It also records who completed a task in `completed_by`, which the task check
reads. ERPNext has the field but never fills it, and Task keeps no version
history, so nothing else says who set the status.
"""
from contextlib import contextmanager

from erpnext.projects.doctype.task import task as erpnext_task
from erpnext.projects.doctype.task.task import Task
import frappe
from frappe.desk.form.assign_to import add, clear

SYSTEM_USERS = {"Administrator", "Guest"}


@contextmanager
def _assignments_kept():
	"""While ERPNext's own status checks run, closing assignments does nothing."""
	original = erpnext_task.close_all_assignments
	erpnext_task.close_all_assignments = lambda *args, **kwargs: False
	try:
		yield
	finally:
		erpnext_task.close_all_assignments = original


class KiluthTask(Task):
	def validate_status(self):
		# Keeps ERPNext's checks (dependencies finished, completed_on set) and
		# drops only the assignment closing.
		with _assignments_kept():
			super().validate_status()
		self.record_completer()

	def record_completer(self):
		if self.status != "Completed":
			self.completed_by = None
		elif self.has_value_changed("status"):
			self.completed_by = frappe.session.user

	def unassign_todo(self):
		if self.status != "Cancelled":
			return
		requester = self.owner
		if requester in SYSTEM_USERS or not frappe.db.get_value("User", requester, "enabled"):
			return  # no real requester: keep whoever is assigned
		current = frappe.parse_json(self.get("_assign") or "[]") or []
		if current == [requester]:
			return
		clear(self.doctype, self.name, ignore_permissions=True)
		add({"doctype": self.doctype, "name": self.name, "assign_to": [requester]})
