"""Account and project managers on a LOCAL THROWAWAY bench. Creates made-up tasks
and projects. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_task_managers.run
"""

import frappe

from kiluth_portal.utils import task_managers as tm

AM, PM, OTHER = "e2e-sales@kiluth.com", "e2e-exec@kiluth.com", "e2e-assignee@kiluth.com"


def _project(name, am=None, pm=None):
	doc = frappe.new_doc("Project")
	doc.project_name = name
	doc.insert(ignore_permissions=True, ignore_mandatory=True, set_name=name)
	frappe.db.set_value("Project", doc.name, {"account_manager": am, "project_manager": pm})
	return doc.name


def _task(subject, **fields):
	return frappe.get_doc({"doctype": "Task", "subject": subject, "status": "Open", **fields}).insert(ignore_permissions=True)


def _people(name):
	return frappe.db.get_value("Task", name, list(tm.FIELDS))


def run():
	frappe.set_user("Administrator")
	results = []

	def check(name, cond):
		results.append((name, bool(cond)))

	tm.ensure_fields()
	frappe.clear_cache(doctype="Task")
	tm.ensure_fields()
	check("safe to run twice", frappe.db.count("Custom Field", {"dt": "Task", "fieldname": "account_manager"}) == 1)
	check("a field already there is not edited", frappe.db.get_value("Custom Field", {"dt": "Task", "fieldname": "account_manager"}, "fieldtype") == "Link")

	p = _project("E2E managers", AM, PM)
	empty = _project("E2E no managers")
	made = [_task("E2E new on a project", project=p)]
	check("new task copies both", _people(made[0].name) == (AM, PM))

	made.append(_task("E2E keeps its own", project=p, account_manager=OTHER))
	check("a name already there stays", _people(made[-1].name) == (OTHER, PM))

	made.append(_task("E2E project without managers", project=empty))
	check("a project with none copies nothing", _people(made[-1].name) == (None, None))

	made.append(_task("E2E no project"))
	check("no project copies nothing", _people(made[-1].name) == (None, None))
	t = made[-1]
	t.reload()
	t.project = p
	t.save(ignore_permissions=True)
	check("getting a project later copies", _people(t.name) == (AM, PM))

	old = _task("E2E old task", project=empty)
	made.append(old)
	frappe.db.set_value("Task", old.name, "project", p)
	old.reload()
	old.priority = "High"
	old.save(ignore_permissions=True)
	check("a later save leaves an old task blank", _people(old.name) == (None, None))

	frappe.db.set_value("Project", p, "account_manager", OTHER)
	made[0].reload()
	made[0].priority = "High"
	made[0].save(ignore_permissions=True)
	check("changing the project does not rewrite tasks", _people(made[0].name) == (AM, PM))
	frappe.db.set_value("Project", p, "account_manager", AM)

	stamp = frappe.db.get_value("Task", old.name, "modified")
	report = tm.backfill_open_tasks()
	check("report only finds it", any(c["task"] == old.name for c in report))
	check("report only writes nothing", _people(old.name) == (None, None))
	tm.backfill_open_tasks(write=1)
	check("backfill fills it", _people(old.name) == (AM, PM))
	check("backfill keeps modified", frappe.db.get_value("Task", old.name, "modified") == stamp)
	check("backfill keeps a name already there", _people(made[1].name) == (OTHER, PM))
	check("run again changes nothing", not any(c["task"] == old.name for c in tm.backfill_open_tasks()))

	for doc in made:
		frappe.delete_doc("Task", doc.name, force=True, ignore_permissions=True)
	for name in (p, empty):
		frappe.delete_doc("Project", name, force=True, ignore_permissions=True)
	frappe.db.commit()
	for name, ok in results:
		print("ok  " if ok else "FAIL", name)
	print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
