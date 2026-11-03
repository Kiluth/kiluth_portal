"""Only the requester, or an admin, completes a task. LOCAL THROWAWAY bench only:
creates made-up tasks and deletes them.

	bench --site notify.localhost execute kiluth_portal.tests.bench_requester_completes.run
"""

import frappe

from kiluth_portal.task_notify import handlers

REQUESTER, DOER, ADMIN = "e2e-sales@kiluth.com", "e2e-member@kiluth.com", "e2e-assigner@kiluth.com"
REFUSED = "Only {} can complete this. Set it to Pending Review so they can check it."


def _task(owner, subject, **fields):
	frappe.set_user(owner)
	task = frappe.get_doc({"doctype": "Task", "subject": subject, "status": "Open", **fields}).insert(ignore_permissions=True)
	frappe.set_user("Administrator")
	return task.name


def _set(name, user, **fields):
	"""Save as `user`. Returns None when saved, else the refusal message."""
	frappe.set_user(user)
	frappe.clear_messages()
	try:
		doc = frappe.get_doc("Task", name)
		doc.update(fields)
		doc.save(ignore_permissions=True)
		return None
	except frappe.ValidationError as e:
		return str(e)
	finally:
		frappe.set_user("Administrator")


def _status(name):
	return frappe.db.get_value("Task", name, ["status", "completed_by"])


def run():
	frappe.set_user("Administrator")
	made, out = [], []
	name = frappe.utils.get_fullname(REQUESTER)
	try:
		t = _task(REQUESTER, "E2E requester completes")
		made.append(t)
		msg = _set(t, DOER, status="Completed")
		out.append(("someone else is refused, with the requester's name", msg == REFUSED.format(name), msg))
		out.append(("refused leaves the status as it was", _status(t)[0] == "Open", _status(t)))
		out.append(("they can set Pending Review", _set(t, DOER, status="Pending Review") is None, _status(t)))
		out.append(("the requester completes it", _set(t, REQUESTER, status="Completed") is None and _status(t) == ("Completed", REQUESTER), _status(t)))

		t2 = _task(REQUESTER, "E2E admin completes")
		made.append(t2)
		out.append(("an admin completes someone's task", _set(t2, ADMIN, status="Completed") is None and _status(t2) == ("Completed", ADMIN), _status(t2)))

		t3 = _task("Administrator", "E2E system task")
		made.append(t3)
		frappe.db.set_value("Task", t3, "owner", "swarm@kiluth.com", update_modified=False)
		msg = _set(t3, DOER, status="Completed")
		out.append(("a task with no requester: others are refused", msg == REFUSED.format("an admin"), msg))
		out.append(("a task with no requester: an admin completes it", _set(t3, ADMIN, status="Completed") is None, _status(t3)))

		# Completed before the rule, by someone who was not the requester.
		t4 = _task(REQUESTER, "E2E completed before the rule")
		made.append(t4)
		frappe.db.set_value("Task", t4, {"status": "Completed", "completed_by": DOER}, update_modified=False)
		out.append(("an old completed task still saves for others", _set(t4, DOER, priority="High") is None, _status(t4)))
		out.append(("and keeps its status and completer", _status(t4) == ("Completed", DOER), _status(t4)))

		t5 = _task(DOER, "E2E own task")
		made.append(t5)
		out.append(("anyone completes a task they asked for", _set(t5, DOER, status="Completed") is None, _status(t5)))

		# The task check posts with Poom's key (here: ADMIN) as swarm@kiluth.com.
		seen = []
		real = handlers._enqueue
		handlers._enqueue = seen.append
		try:
			frappe.db.set_value("Task", t2, "_assign", frappe.as_json([DOER]), update_modified=False)
			frappe.set_user(ADMIN)
			for content, by in (("<p><b>Task check:</b> this task breaks Working with Tasks.</p>", "Task check"),
			                    ("<p>A person's comment.</p>", None)):
				frappe.get_doc({"doctype": "Comment", "comment_type": "Comment", "reference_doctype": "Task",
				                "reference_name": t2, "content": content, "comment_email": "swarm@kiluth.com",
				                "comment_by": by or "Kiluth Swarm"}).insert(ignore_permissions=True)
		finally:
			handlers._enqueue = real
			frappe.set_user("Administrator")
		check, person = seen
		out.append(("a check comment tells the requester and the assignee",
		            check["recipients"] == sorted([REQUESTER, DOER]) and check["payload"]["title"].startswith("Task check on"), check["recipients"]))
		out.append(("a person's comment still tells the assignee only", person["recipients"] == [DOER], person["recipients"]))
	finally:
		for t in made:
			frappe.db.delete("Comment", {"reference_doctype": "Task", "reference_name": t})
			frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(ok for _, ok, _ in out)}/{len(out)}")
