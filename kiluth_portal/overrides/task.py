"""Keep the name on a completed Task.

ERPNext's Task closes every assignment when a task is completed, and again on
every later save of a completed task (`validate_status` and `unassign_todo` in
erpnext/projects/doctype/task/task.py). Kiluth's Task Usage Guideline needs the
opposite: a finished task keeps its holder, the person who did the work, so
anyone can see who to ask about that area later ("How a Task Moves").

So completed tasks keep their assignees. Cancelled tasks behave as ERPNext
intends: nothing was delivered, so nobody holds them.
"""
from contextlib import contextmanager

from erpnext.projects.doctype.task import task as erpnext_task
from erpnext.projects.doctype.task.task import Task
from frappe.desk.form.assign_to import clear


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

	def unassign_todo(self):
		if self.status == "Cancelled":
			clear(self.doctype, self.name)
