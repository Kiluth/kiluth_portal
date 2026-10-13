"""End-to-end check of the Task notify listener on a LOCAL THROWAWAY bench.

Needs a running RQ worker on the `short` queue. Creates made-up users and a
made-up Task. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_notify_e2e.run

Not named test_*, so the Frappe test runner and the pure-Python oracle skip it.
"""

import time

import frappe
from frappe.desk.form.assign_to import add as assign
from frappe.desk.form.utils import add_comment

from kiluth_portal.task_notify import handlers, jobs, outbox

ASSIGNER = "e2e-assigner@kiluth.com"
ASSIGNEE = "e2e-assignee@kiluth.com"
DOCTYPE = jobs.DOCTYPE


def _user(email, first_name):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"roles": [{"role": "Projects User"}, {"role": "System Manager"}],
			}
		).insert(ignore_permissions=True)


def _rows(task):
	return frappe.get_all(
		DOCTYPE,
		filters={"task": task},
		fields=["event_id", "event_type", "recipient", "channel", "status", "attempts", "last_error"],
		order_by="creation asc",
	)


def _wait(task, count, timeout=30):
	"""Wait until the worker has written `count` rows (and they've left Queued)."""
	end = time.time() + timeout
	while time.time() < end:
		frappe.db.rollback()  # fresh snapshot of what the worker committed
		rows = _rows(task)
		if len(rows) >= count and all(r.status != "Queued" for r in rows):
			return rows
		time.sleep(0.5)
	return _rows(task)


def _settle(task, seconds=4):
	"""For 'expect nothing new' checks: give the worker time, then read."""
	time.sleep(seconds)
	frappe.db.rollback()
	return _rows(task)


def _as(user):
	frappe.set_user(user)


def run():
	results = []

	def check(name, ok, detail):
		results.append((name, ok))
		print(("PASS " if ok else "FAIL ") + name + " :: " + str(detail))

	_as("Administrator")
	_user(ASSIGNER, "E2E Assigner")
	_user(ASSIGNEE, "E2E Assignee")
	task = frappe.get_doc({"doctype": "Task", "subject": f"E2E notify {frappe.generate_hash(length=6)}"}).insert(
		ignore_permissions=True
	)
	frappe.db.commit()

	# 1. Assign: one Sent row on `log` for the assignee.
	_as(ASSIGNER)
	assign({"doctype": "Task", "name": task.name, "assign_to": [ASSIGNEE], "description": task.subject})
	frappe.db.commit()
	rows = _wait(task.name, 1)
	check(
		"assign -> one Sent log row for assignee",
		len(rows) == 1
		and rows[0].event_type == "task.assigned"
		and rows[0].recipient == ASSIGNEE
		and rows[0].channel == "log"
		and rows[0].status == "Sent",
		rows,
	)

	# 2. Comment by someone else: one row for the assignee.
	add_comment("Task", task.name, "<p>Can you look at this?</p>", ASSIGNER, "E2E Assigner")
	frappe.db.commit()
	rows = _wait(task.name, 2)
	commented = [r for r in rows if r.event_type == "task.commented"]
	check(
		"other's comment -> one Sent row for assignee",
		len(commented) == 1 and commented[0].recipient == ASSIGNEE and commented[0].status == "Sent",
		commented,
	)

	# 3. Comment by the assignee: no row.
	_as(ASSIGNEE)
	add_comment("Task", task.name, "<p>On it.</p>", ASSIGNEE, "E2E Assignee")
	frappe.db.commit()
	rows = _settle(task.name)
	check("assignee's own comment -> no row", len(rows) == 2, rows)

	# 4. Replay: the same assignment event again, through the hook and the job.
	_as(ASSIGNER)
	todo = frappe.get_all(
		"ToDo", filters={"reference_type": "Task", "reference_name": task.name, "allocated_to": ASSIGNEE}, pluck="name"
	)[0]
	handlers.on_todo_change(frappe.get_doc("ToDo", todo))  # fresh doc: no before-save, same modified
	frappe.db.commit()
	rows = _settle(task.name)
	check("replay via hook + worker -> no duplicate", len(rows) == 2, rows)

	# Same again, synchronously in this process, to hit the unique-index path directly.
	first = frappe.get_all(DOCTYPE, filters={"task": task.name, "event_type": "task.assigned"}, pluck="dedupe_key")[0]
	inserted = jobs.FrappeStore().insert(
		{
			"dedupe_key": first,
			"event_id": "replay",
			"event_type": "task.assigned",
			"task": task.name,
			"actor": ASSIGNER,
			"recipient": ASSIGNEE,
			"channel": "log",
			"payload": {},
			"status": outbox.QUEUED,
			"attempts": 0,
		}
	)
	rows = _rows(task.name)
	check("direct duplicate insert -> refused, no row", inserted is False and len(rows) == 2, rows)

	_as("Administrator")
	failed = [n for n, ok in results if not ok]
	print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED: {failed}" if failed else ""))
	return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}
