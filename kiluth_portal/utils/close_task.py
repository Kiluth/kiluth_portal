"""Create the month's close task on the 1st.

Implements step 1 of docs.kiluth.com/finance/monthly-close: on the 1st the
Kiluth Portal creates "Close the books for <last month>" and assigns it to the
statement supplier. The supplier attaches the statements and hands the task to
Kiluth Swarm, which runs the close.

The supplier is a site default (`kiluth_close_statement_supplier`) so it can
change without a code change; it falls back to Poom.

Idempotent: if the task for that month already exists, nothing happens. An
hourly catch-up covers a missed cron minute, the same way the monthly financial
report does.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, getdate, nowdate

from kiluth_portal.utils.close_report import SUBJECT_PREFIX

SUPPLIER_KEY = "kiluth_close_statement_supplier"
DEFAULT_SUPPLIER = "poom.pengcharoen@kiluth.com"
PROJECT = "PROJ-0001"
DEPARTMENT = "Finance - K"
DOC_URL = "https://docs.kiluth.com/finance/monthly-close"


def _subject_for(today) -> str:
	last_month = add_months(getdate(today).replace(day=1), -1)
	return f"{SUBJECT_PREFIX}{last_month.strftime('%B %Y')}"


def _description(month_label: str) -> str:
	return (
		f"Monthly close, per <a href=\"{DOC_URL}\">Monthly Close</a>.<br><br>"
		f"<b>Attach by the 2nd</b><br>"
		f"• Bank statement for {month_label}<br>"
		f"• Card statement(s) for {month_label}<br>"
		f"• Any receipts and 50 ทวิ certificates received<br><br>"
		f"Then assign this task to Kiluth Swarm; the close starts by itself.<br><br>"
		f"Done when the books for {month_label} are closed, the Portal matches the bank, "
		f"and any return is filed."
	)


def create_close_task():
	"""Cron: 08:00 on the 1st. Safe to call any time; creates at most one task per month."""
	subject = _subject_for(nowdate())
	if frappe.db.exists("Task", {"subject": subject}):
		return None

	month_label = subject[len(SUBJECT_PREFIX):]
	task = frappe.get_doc({
		"doctype": "Task",
		"subject": subject,
		"project": PROJECT,
		"department": DEPARTMENT,
		"status": "Open",
		"exp_end_date": getdate(nowdate()).replace(day=4),
		"description": _description(month_label),
	}).insert(ignore_permissions=True)

	supplier = frappe.db.get_default(SUPPLIER_KEY) or DEFAULT_SUPPLIER
	from frappe.desk.form.assign_to import add as assign
	assign({"doctype": "Task", "name": task.name, "assign_to": [supplier]})
	frappe.db.commit()
	return task.name


def create_close_task_catchup():
	"""Hourly: if today is the 1st–4th and the month's task is missing, create it."""
	if getdate(nowdate()).day <= 4:
		create_close_task()
