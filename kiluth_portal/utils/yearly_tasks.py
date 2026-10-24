"""Raise the yearly and half-yearly tax tasks so they can't be forgotten.

Kiluth's FY 2025 corporate return and financial statements went unfiled
because nothing reminded anyone: the monthly close has a task, the year did
not. These create one task per return, early enough to act on, the same way
`close_task` creates the monthly close.

Kiluth's financial year is the calendar year. Deadlines below assume that:

| Task                         | Created   | Due                                    |
| ---------------------------- | --------- | -------------------------------------- |
| ภ.ง.ด.1ก for the year         | 5 January | end of February                        |
| ภ.ง.ด.50 + financial statements | 5 January | end of May (150 days after year end)   |
| ภ.ง.ด.51 for the first half   | 5 July    | 31 August (+8 days if filed online)    |

The ภ.ง.ด.50 and ภ.ง.ด.51 dates are the Revenue Department's. The deadline for
the financial statements to the Department of Business Development is not
hardcoded: it depends on when the shareholders approve them, so the task asks
the accountant to set it.

Idempotent: a task is matched by its subject, so a repeat run creates nothing.
A daily catch-up covers a missed cron or a server that was down on the day.

Rules: docs.kiluth.com/finance/tax
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate

PROJECT = "PROJ-0001"
DEPARTMENT = "Finance - K"
OWNER_KEY = "kiluth_tax_task_owner"
DEFAULT_OWNER = "poom.pengcharoen@kiluth.com"
DOC_URL = "https://docs.kiluth.com/finance/tax"


def _owner() -> str:
	return frappe.db.get_default(OWNER_KEY) or DEFAULT_OWNER


def _create(subject: str, due, description: str) -> str | None:
	if frappe.db.exists("Task", {"subject": subject}):
		return None
	task = frappe.get_doc({
		"doctype": "Task",
		"subject": subject,
		"project": PROJECT,
		"department": DEPARTMENT,
		"status": "Open",
		"priority": "High",
		"exp_end_date": due,
		"description": description,
	}).insert(ignore_permissions=True)
	from frappe.desk.form.assign_to import add as assign

	assign({"doctype": "Task", "name": task.name, "assign_to": [_owner()]})
	frappe.db.commit()
	return task.name


def _footer() -> str:
	return (
		f"<br><br>Rules: <a href=\"{DOC_URL}\">Tax</a>. Finance prepares; a director or the "
		f"accountant files. Kiluth has no accountant engaged yet — if that is still true, "
		f"engaging one is the first step."
	)


def year_end_tasks():
	"""Cron: 08:00 on 5 January. Raises the two returns for the year just ended."""
	year = getdate(nowdate()).year - 1

	_create(
		f"File ภ.ง.ด.1ก for {year}",
		getdate(f"{year + 1}-02-28"),
		f"Yearly summary of income tax withheld from salaries paid in {year}, and each "
		f"employee's 50 ทวิ for the year.<br><br>"
		f"<b>Due by the end of February {year + 1}.</b><br><br>"
		f"<b>Done when</b> ภ.ง.ด.1ก for {year} is filed, the filing reference is a comment "
		f"here, and every employee has their 50 ทวิ."
		+ _footer(),
	)

	_create(
		f"Close {year} and file ภ.ง.ด.50 and the financial statements",
		getdate(f"{year + 1}-05-30"),
		f"Year-end for {year}: close the books, prepare the financial statements, file the "
		f"corporate income tax return, and send the statements to the Department of Business "
		f"Development.<br><br>"
		f"<b>ภ.ง.ด.50 is due by the end of May {year + 1}</b> (150 days after year end). "
		f"Claim back the withholding certificates (50 ทวิ) clients gave Kiluth during {year}.<br><br>"
		f"<b>The financial statements' deadline</b> depends on when the shareholders approve "
		f"them. The accountant should set it as a comment here on day one.<br><br>"
		f"<b>Done when</b> ภ.ง.ด.50 is filed, the statements are submitted, and both "
		f"references are comments here."
		+ _footer(),
	)


def half_year_task():
	"""Cron: 08:00 on 5 July. Raises the half-year corporate return."""
	year = getdate(nowdate()).year
	_create(
		f"File ภ.ง.ด.51 for the first half of {year}",
		getdate(f"{year}-08-31"),
		f"Half-year corporate income tax return for January–June {year}.<br><br>"
		f"<b>Due by 31 August {year}</b>, or 8 days later if filed online.<br><br>"
		f"<b>Done when</b> ภ.ง.ด.51 is filed and its reference is a comment here."
		+ _footer(),
	)


def yearly_tasks_catchup():
	"""Daily: if the month's task is missing, create it. Covers a missed cron."""
	today = getdate(nowdate())
	if today.month == 1 and today.day >= 5:
		year_end_tasks()
	elif today.month == 7 and today.day >= 5:
		half_year_task()
