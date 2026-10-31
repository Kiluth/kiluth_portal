"""Jobs that find tasks by title, on a LOCAL THROWAWAY bench. Makes made-up tasks.
Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_ops_titles.run
"""

from unittest import mock

import frappe

from kiluth_portal.kiluth_hr import learning_report as lr
from kiluth_portal.utils import close_report, close_task, lead_routing, tax_checks, yearly_tasks
from kiluth_portal.utils.task_titles import same_title


def _tasks(title):
	return [frappe.db.get_value("Task", n, "subject") for n in same_title(title)]


def _clear(*names):
	for n in names:
		frappe.delete_doc("Task", n, force=True, ignore_permissions=True)


def run():
	frappe.set_user("Administrator")
	results = []

	def check(name, cond, extra=""):
		results.append((name, bool(cond), extra))

	if not frappe.db.exists("Department", "Finance - K"):
		doc = frappe.new_doc("Department")
		doc.name, doc.department_name = "Finance - K", "Finance"
		doc.db_insert()
	frappe.db.set_default(close_task.SUPPLIER_KEY, "Administrator")
	frappe.db.set_default(yearly_tasks.OWNER_KEY, "Administrator")
	# Close the books: the month's title, created twice, then renamed both ways.
	title = close_task._subject_for(frappe.utils.nowdate())
	_clear(*same_title(title))
	first = close_task.create_close_task()
	check("close: new title has the department", frappe.db.get_value("Task", first, "subject") == f"[Finance] {title}")
	check("close: second run makes no duplicate", close_task.create_close_task() is None and len(_tasks(title)) == 1)
	frappe.db.set_value("Task", first, "subject", title)
	check("close: a task without the prefix also counts", close_task.create_close_task() is None and len(_tasks(title)) == 1)
	frappe.db.set_value("Task", first, "subject", f"[Finance] {title}")

	sent = []
	doc = frappe.get_doc("Task", first)
	before = mock.Mock(status="Open")
	with mock.patch.object(close_report.frappe, "enqueue", lambda *a, **k: sent.append(k)), mock.patch.object(doc, "get_doc_before_save", lambda: before):
		doc.status = "Completed"
		close_report.on_task_update(doc)
	check("close: completing the prefixed task queues the report", len(sent) == 1)
	check("close: month read through the prefix", close_report._period_from_subject(doc.subject)["label"] == title.removeprefix(close_report.SUBJECT_PREFIX))
	_clear(first)

	# Yearly and tax jobs, same lookup.
	made = yearly_tasks._create("E2E File something for 2099", frappe.utils.nowdate(), "Done when filed.")
	check("yearly: department in the title", frappe.db.get_value("Task", made, "subject") == "[Finance] E2E File something for 2099")
	check("yearly: no duplicate", yearly_tasks._create("E2E File something for 2099", frappe.utils.nowdate(), "x") is None)
	_clear(made)
	made = tax_checks._raise_task("E2E Withholding tax for 2099", "Done when dealt with.")
	check("tax: department in the title", frappe.db.get_value("Task", made, "subject") == "[Finance] E2E Withholding tax for 2099")
	check("tax: no duplicate", tax_checks._raise_task("E2E Withholding tax for 2099", "x") is None)
	_clear(made)

	# Learning report: one open task per title.
	a = lr._open_task("E2E Check the docs", "Done when checked.", "Administrator", "Finance - K")
	check("learning: department in the title", frappe.db.get_value("Task", a, "subject") == "[Finance] E2E Check the docs")
	check("learning: reuses the open task", lr._open_task("E2E Check the docs", "x", "Administrator", "Finance - K") == a)
	_clear(a)

	# Leads.
	lead = "CRM-LEAD-E2E-1"
	check("lead: title", lead_routing.lead_task_title(lead) == f"[Account Management] Qualify lead: {lead}")
	t = frappe.get_doc({"doctype": "Task", "subject": lead_routing.lead_task_title(lead), "status": "Open"}).insert(ignore_permissions=True)
	check("lead: finds its open task", lead_routing.open_lead_task(lead) == t.name)
	check("lead: read back from the title", lead_routing.bare(t.subject)[len(lead_routing.SUBJECT_PREFIX):] == lead)
	_clear(t.name)
	frappe.db.commit()
	for name, ok, extra in results:
		print("ok  " if ok else "FAIL", name, extra)
	print(f"{sum(ok for _, ok, _e in results)}/{len(results)} passed")
