"""completed_by on a LOCAL THROWAWAY bench. Creates a made-up task.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_completer.run
"""

import frappe

ONE, TWO = "e2e-sales@kiluth.com", "e2e-exec@kiluth.com"


def _set_status(name, status, user):
	frappe.set_user(user)
	doc = frappe.get_doc("Task", name)
	doc.status = status
	doc.save(ignore_permissions=True)
	frappe.set_user("Administrator")


def run():
	frappe.set_user("Administrator")
	results = []
	task = frappe.get_doc({"doctype": "Task", "subject": "E2E completer", "status": "Open"}).insert(ignore_permissions=True)
	who = lambda: frappe.db.get_value("Task", task.name, "completed_by")

	results.append(("open has none", who() is None))
	_set_status(task.name, "Completed", ONE)
	results.append(("records who set Completed", who() == ONE))
	doc = frappe.get_doc("Task", task.name)
	doc.priority = "High"
	frappe.set_user(TWO)
	doc.save(ignore_permissions=True)
	frappe.set_user("Administrator")
	results.append(("a later save by someone else keeps it", who() == ONE))
	_set_status(task.name, "Working", TWO)
	results.append(("reopening clears it", who() is None))
	_set_status(task.name, "Completed", TWO)
	results.append(("completing again records the new person", who() == TWO))

	frappe.delete_doc("Task", task.name, force=True, ignore_permissions=True)
	frappe.db.commit()
	for name, ok in results:
		print("ok  " if ok else "FAIL", name)
	print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
