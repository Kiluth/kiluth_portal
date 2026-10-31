"""Lead escalation on a LOCAL THROWAWAY bench: the task moves, one name stays.

Creates made-up users, a Lead and a Task. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_lead_escalation.run
"""

from datetime import timedelta
from unittest import mock

import frappe

from kiluth_portal.utils import lead_routing as lr

SALES = "e2e-sales@kiluth.com"
EXEC = "e2e-exec@kiluth.com"
EXEC2 = "e2e-exec2@kiluth.com"


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"roles": [{"role": "Projects User"}]}).insert(ignore_permissions=True)


def _names(task):
	return frappe.get_all("ToDo", filters={"reference_type": "Task", "reference_name": task, "status": "Open"}, pluck="allocated_to")


def _scenario(executives):
	# Deleted tasks leave their ToDos and comments, and the series can hand the name out again.
	frappe.db.delete("ToDo", {"allocated_to": ["in", [SALES, EXEC, EXEC2]]})
	frappe.db.delete("Comment", {"reference_doctype": "Task", "content": lr.ESCALATED})
	lead = frappe.get_doc({"doctype": "Lead", "lead_name": "E2E Lead", "qualification_status": "Unqualified"}).insert(ignore_permissions=True)
	task = frappe.get_doc({"doctype": "Task", "subject": f"{lr.SUBJECT_PREFIX}{lead.name}", "status": "Open"}).insert(ignore_permissions=True)
	lr.assign(task.name, task.subject, [SALES])
	frappe.db.set_value("Task", task.name, "creation", frappe.utils.now_datetime() - timedelta(days=10))
	with mock.patch.object(lr, "users_with_role", lambda role: executives):
		lr.escalate_unanswered_leads()
		first = _names(task.name)
		lr.escalate_unanswered_leads()  # a second hour changes nothing
		second = _names(task.name)
	comments = frappe.db.count("Comment", {"reference_doctype": "Task", "reference_name": task.name, "content": lr.ESCALATED})
	frappe.delete_doc("Task", task.name, force=True, ignore_permissions=True)
	frappe.delete_doc("Lead", lead.name, force=True, ignore_permissions=True)
	return first, second, comments


def run():
	frappe.set_user("Administrator")
	for u in (SALES, EXEC, EXEC2):
		_user(u)
	results = []
	first, second, comments = _scenario([EXEC])
	results.append(("one executive: exactly that name", first == [EXEC]))
	results.append(("one executive: same after a second hour", second == [EXEC]))
	results.append(("one executive: one comment", comments == 1))
	first, second, comments = _scenario([SALES])
	results.append(("holder is the executive: stays", first == [SALES]))
	first, second, comments = _scenario([EXEC, EXEC2])
	results.append(("two executives: nobody picked, holder stays", first == [SALES]))
	results.append(("two executives: one comment", comments == 1))
	frappe.db.commit()
	for name, ok in results:
		print("ok  " if ok else "FAIL", name)
	print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
