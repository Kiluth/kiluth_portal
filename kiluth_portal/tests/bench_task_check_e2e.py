"""End-to-end check of the task check triggers on a LOCAL THROWAWAY bench.

Creates made-up tasks, nothing is sent to AWS: the job is recorded instead of
queued. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_check_e2e.run

Not named test_*, so the Frappe test runner and the pure-Python oracle skip it.
"""

from unittest import mock

import frappe
from frappe.desk.form import assign_to
from frappe.desk.form.assign_to import add as assign
from frappe.desk.form.utils import add_comment

from kiluth_portal.task_check import handlers

QUEUE = "https://sqs.invalid/queue"


def _task(subject, description="Done when it works."):
	return frappe.get_doc({"doctype": "Task", "subject": subject, "description": description, "status": "Open"}).insert(ignore_permissions=True)


def _fields():
	# Live, these two were made by hand and are not in the fixtures.
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	create_custom_field("Task", {"fieldname": "hygiene", "label": "Hygiene", "fieldtype": "Select", "options": "\nPass\nFail", "read_only": 1})
	create_custom_field("Task", {"fieldname": "hygiene_note", "label": "Hygiene Note", "fieldtype": "Small Text", "read_only": 1})


def run():
	frappe.set_user("Administrator")
	_fields()
	sent, results = [], []

	def check(name, cond):
		results.append((name, bool(cond)))

	def verdict(name, value):
		frappe.db.set_value("Task", name, {"hygiene": value, "hygiene_note": None}, update_modified=False)

	def drain():
		out = list(sent)
		sent.clear()
		return out

	def record(method, **kw):
		if method.endswith("task_check.jobs.send"):
			sent.append(kw["task"])

	frappe.local.conf["task_check_queue_url"] = QUEUE
	with mock.patch.object(handlers.frappe, "enqueue", record):
		a = _task("E2E check: blocker")
		check("create runs", drain().count(a.name) >= 1)
		check("create leaves it not checked", frappe.db.get_value("Task", a.name, "hygiene") in ("", None))

		verdict(a.name, "Pass")
		t = frappe.get_doc("Task", a.name)
		t.subject = "E2E check: blocker, renamed"
		t.save(ignore_permissions=True)
		check("title runs", drain() == [a.name])
		check("title clears Pass", not frappe.db.get_value("Task", a.name, "hygiene"))

		verdict(a.name, "Pass")
		t = frappe.get_doc("Task", a.name)
		t.description = "Done when it really works."
		t.save(ignore_permissions=True)
		check("description runs", drain() == [a.name])

		b = _task("E2E check: blocked")
		drain()
		verdict(b.name, "Pass")
		t = frappe.get_doc("Task", b.name)
		t.append("depends_on", {"task": a.name})
		t.save(ignore_permissions=True)
		check("dependency added runs", drain() == [b.name])

		verdict(b.name, "Pass")
		t = frappe.get_doc("Task", b.name)
		t.priority = "High"
		t.save(ignore_permissions=True)
		check("another field does not run", drain() == [])
		check("another field keeps the verdict", frappe.db.get_value("Task", b.name, "hygiene") == "Pass")

		# The checker's own write: the same PUT its REST call makes.
		t = frappe.get_doc("Task", b.name)
		t.update({"hygiene": "Fail", "hygiene_note": "x"})
		t.save(ignore_permissions=True)
		check("the checker's own write does not run", drain() == [])
		check("the checker's own write stays", frappe.db.get_value("Task", b.name, "hygiene") == "Fail")

		add_comment("Task", b.name, "A plain comment", "Administrator", "Administrator")
		check("a comment does not run", drain() == [])

		f = frappe.get_doc({"doctype": "File", "file_name": "e2e.txt", "content": "x", "is_private": 1,
			"attached_to_doctype": "Task", "attached_to_name": b.name}).insert(ignore_permissions=True)
		check("an attachment does not run", drain() == [])
		f.delete()

		verdict(b.name, "Pass")
		assign({"doctype": "Task", "name": b.name, "assign_to": ["Administrator"]})
		check("assignee added runs", b.name in drain())
		check("assignee added clears Pass", not frappe.db.get_value("Task", b.name, "hygiene"))

		verdict(b.name, "Pass")
		assign_to.clear("Task", b.name, ignore_permissions=True)
		check("assignee removed runs", b.name in drain())

		frappe.local.conf.pop("task_check_queue_url")
		t = frappe.get_doc("Task", b.name)
		verdict(b.name, "Pass")
		t.reload()
		t.subject = "E2E check: switched off"
		t.save(ignore_permissions=True)
		check("off switch: no run", drain() == [])
		check("off switch: verdict stays", frappe.db.get_value("Task", b.name, "hygiene") == "Pass")

	frappe.delete_doc("Task", b.name, force=True, ignore_permissions=True)
	frappe.delete_doc("Task", a.name, force=True, ignore_permissions=True)
	frappe.db.commit()
	for name, ok in results:
		print("ok  " if ok else "FAIL", name)
	print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
