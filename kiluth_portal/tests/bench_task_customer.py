"""A task's Customer follows its project, on a LOCAL THROWAWAY bench. Makes up
customers, projects and tasks, then deletes them. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_customer.run
"""

import frappe

from kiluth_portal.utils import task_customer as tc

C1, C2 = "E2E Customer One", "E2E Customer Two"
P1, P2 = "E2E-CUST-P1", "E2E-CUST-P2"
MEMBER = "e2e-member@kiluth.com"


def _customer(name):
	frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company",
	                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
	                "territory": frappe.db.get_value("Territory", {"is_group": 0}),
	                "custom_unique_email_id": f"{name.lower().replace(' ', '-')}@e2e.local"}).insert(ignore_permissions=True)


def _project(name, customer=None):
	doc = frappe.new_doc("Project")
	doc.project_name = name
	doc.customer = customer
	doc.insert(ignore_permissions=True, ignore_mandatory=True, set_name=name)
	return doc.name


def _task(subject, project=None):
	return frappe.get_doc({"doctype": "Task", "subject": subject, "status": "Open", "project": project}).insert(ignore_permissions=True).name


def _customer_of(task):
	return frappe.db.get_value("Task", task, "customer")


def _save_project(name, customer):
	doc = frappe.get_doc("Project", name)
	doc.customer = customer
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)


def run():
	frappe.set_user("Administrator")
	out, tasks = [], []
	# ERPNext re-saves the project after a task save; on the bench projects have no Company.
	from erpnext.projects.doctype.task.task import Task
	real_update = Task.update_project
	Task.update_project = lambda self: None
	try:
		tc.ensure_field()
		frappe.clear_cache(doctype="Task")
		tc.ensure_field()
		out.append(("safe to run twice", frappe.db.count("Custom Field", {"dt": "Task", "fieldname": "customer"}) == 1, None))
		df = frappe.get_meta("Task").get_field("customer")
		shape = (df.fieldtype, df.options, df.fetch_from, df.read_only, df.in_standard_filter, df.in_list_view)
		out.append(("field: read-only Link to Customer, from project.customer, a filter and a list column",
		            shape == ("Link", "Customer", "project.customer", 1, 1, 1), shape))

		for c in (C1, C2):
			_customer(c)
		_project(P1, C1)
		_project(P2)

		on_p1 = _task("E2E customer on P1", P1)
		no_project = _task("E2E customer none")
		tasks += [on_p1, no_project]
		out.append(("new task takes its project's customer", _customer_of(on_p1) == C1, _customer_of(on_p1)))
		out.append(("task with no project stays blank", not _customer_of(no_project), _customer_of(no_project)))

		doc = frappe.get_doc("Task", on_p1)
		doc.project = P2
		doc.save(ignore_permissions=True)
		out.append(("moved to a project with no customer: blank", not _customer_of(on_p1), _customer_of(on_p1)))
		doc = frappe.get_doc("Task", on_p1)
		doc.project = P1
		doc.save(ignore_permissions=True)
		out.append(("moved back: customer again", _customer_of(on_p1) == C1, _customer_of(on_p1)))

		second = _task("E2E customer on P1, second", P1)
		tasks.append(second)
		before = {t: str(frappe.db.get_value("Task", t, "modified")) for t in (on_p1, second)}
		versions = frappe.db.count("Version", {"ref_doctype": "Task", "docname": ["in", [on_p1, second]]})
		_save_project(P1, C2)
		out.append(("project's customer changes: all its tasks follow",
		            [_customer_of(t) for t in (on_p1, second)] == [C2, C2], [_customer_of(t) for t in (on_p1, second)]))
		out.append(("...quietly: tasks' modified unchanged, no new Version rows",
		            before == {t: str(frappe.db.get_value("Task", t, "modified")) for t in (on_p1, second)}
		            and versions == frappe.db.count("Version", {"ref_doctype": "Task", "docname": ["in", [on_p1, second]]}), None))
		_save_project(P1, None)
		out.append(("project's customer cleared: its tasks go blank", not _customer_of(on_p1) and not _customer_of(second), None))
		_save_project(P1, C2)

		# Backfill: tasks from before the field, and any that drifted.
		frappe.db.set_value("Task", on_p1, "customer", None, update_modified=False)
		frappe.db.set_value("Task", second, "customer", C1, update_modified=False)
		frappe.db.set_value("Task", no_project, "customer", C1, update_modified=False)
		changed = tc.sync_all()
		out.append(("backfill fixes blank, wrong, and no-project tasks",
		            [_customer_of(t) for t in tasks] == [C2, None, C2] and changed >= 3, ([_customer_of(t) for t in tasks], changed)))
		out.append(("backfill again changes nothing", tc.sync_all() == 0, None))

		frappe.set_user(MEMBER)
		try:
			seen = frappe.get_list("Task", filters={"customer": C2}, pluck="name")
		finally:
			frappe.set_user("Administrator")
		out.append(("a member filters the Task list by Customer", sorted(seen) == sorted([on_p1, second]), seen))
	finally:
		Task.update_project = real_update
		frappe.set_user("Administrator")
		for t in tasks:
			for dt, key in (("Comment", "reference_name"), ("ToDo", "reference_name"), ("Version", "docname")):
				frappe.db.delete(dt, {key: t})
			frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
		for p in (P1, P2):
			frappe.db.delete("Version", {"ref_doctype": "Project", "docname": p})
			frappe.db.delete("Project", {"name": p})
		for c in (C1, C2):
			frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": c})
			if frappe.db.exists("Customer", c):
				frappe.delete_doc("Customer", c, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(ok for _, ok, _ in out)}/{len(out)}")
