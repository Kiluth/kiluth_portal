"""Who qualifies a website lead, and what happens if nobody does.

Lead Intake (docs.kiluth.com/marketing/lead-intake) has a person in Marketing
pick the salesperson. A website lead has no such person, so the Portal picks:

- Routing: every enabled user with the "Sales" role is in the pool (give the
  role only to certified salespeople, docs.kiluth.com/hr/certification). The
  new "Qualify lead" task goes to whoever has the fewest open ones. With
  nobody in Sales it goes to FALLBACK, so no lead is ever left unassigned.
- Escalation: if nobody has touched the lead one working day later (Thai
  public holidays and weekends skipped), the task is also assigned to the
  "Executive" role, who steps in per Lead Intake.

Not a Frappe Assignment Rule on Task on purpose: in Frappe 16 any rule on a
doctype reopens closed assignments whenever any document of that type is
saved, which would undo every hand-back on every Task (Poom, 2026-10-24).
"""

from __future__ import annotations

import frappe
from frappe.desk.form import assign_to
from frappe.utils import get_datetime, now_datetime

from kiluth_portal.utils.lead_rules import least_loaded, one_working_day_after

SALES_ROLE = "Sales"
ESCALATION_ROLE = "Executive"
FALLBACK = "phuttipan.samranruen@kiluth.com"  # Reaw, the only salesperson today
SUBJECT_PREFIX = "Qualify lead: "
ESCALATED = "Escalated: nobody touched this lead within one working day."
HOLIDAY_LIST = "Kiluth Thailand Holiday {year}"
NOT_PEOPLE = ("Administrator", "Guest", "website-bot@kiluth.com")


def users_with_role(role: str) -> list[str]:
	return frappe.get_all(
		"User",
		filters=[["Has Role", "role", "=", role], ["enabled", "=", 1], ["name", "not in", NOT_PEOPLE]],
		pluck="name",
		distinct=True,
	)


def pick_salesperson() -> str:
	"""The Sales user with the fewest open "Qualify lead" tasks, or FALLBACK."""
	team = users_with_role(SALES_ROLE)
	if not team:
		return FALLBACK
	rows = frappe.db.sql(
		"""
		select t.allocated_to, sum(t.status = 'Open'), max(t.creation)
		from `tabToDo` t join `tabTask` k on k.name = t.reference_name
		where t.reference_type = 'Task' and k.subject like %(prefix)s and t.allocated_to in %(team)s
		group by t.allocated_to
		""",
		{"prefix": SUBJECT_PREFIX + "%", "team": tuple(team)},
	)
	seen = {user: (int(open_ or 0), last) for user, open_, last in rows}
	loads = [(user, *seen.get(user, (0, None))) for user in team]
	return least_loaded(loads) or FALLBACK


def assign(task_name: str, subject: str, users: list[str]) -> None:
	# Private _add: the public add() always checks permissions in Frappe 16,
	# and the website bot and the scheduler have none on Task.
	assign_to._add(
		{"assign_to": users, "doctype": "Task", "name": task_name, "description": subject},
		ignore_permissions=True,
	)


def _holidays(*years: int) -> set:
	days = set()
	for year in years:
		name = HOLIDAY_LIST.format(year=year)
		if frappe.db.exists("Holiday List", name):
			days.update(
				d.holiday_date
				for d in frappe.get_all(
					"Holiday", filters={"parent": name, "parenttype": "Holiday List"}, fields=["holiday_date"]
				)
			)
	return days


def _touched(task, lead_name: str) -> bool:
	"""Anything a person did on the lead or its task since the task was made."""
	since = task.creation
	if frappe.db.get_value("Lead", lead_name, "qualification_status") != "Unqualified":
		return True
	if frappe.db.get_value("Lead", lead_name, "status") == "Do Not Contact":
		return True
	for ref_type, ref_name in (("Task", task.name), ("Lead", lead_name)):
		if frappe.db.exists(
			"Comment",
			{
				"reference_doctype": ref_type,
				"reference_name": ref_name,
				"comment_type": "Comment",
				"creation": (">", since),
			},
		):
			return True
	return bool(frappe.db.exists(
		"Communication", {"reference_doctype": "Lead", "reference_name": lead_name, "creation": (">", since)}
	))


def escalate_unanswered_leads():
	"""Hourly: give untouched "Qualify lead" tasks to the Executive role too, once."""
	now = now_datetime()
	tasks = frappe.get_all(
		"Task",
		filters={"subject": ("like", SUBJECT_PREFIX + "%"), "status": "Open"},
		fields=["name", "subject", "creation"],
		limit=200,
	)
	if not tasks:
		return
	holidays = _holidays(now.year - 1, now.year, now.year + 1)
	executives = users_with_role(ESCALATION_ROLE)
	for task in tasks:
		if now < one_working_day_after(get_datetime(task.creation), holidays):
			continue
		done = {"reference_doctype": "Task", "reference_name": task.name, "content": ESCALATED}
		if frappe.db.exists("Comment", done):
			continue
		lead_name = task.subject[len(SUBJECT_PREFIX):].strip()
		if not frappe.db.exists("Lead", lead_name) or _touched(task, lead_name):
			continue
		assigned = set(frappe.get_all(
			"ToDo",
			filters={"reference_type": "Task", "reference_name": task.name, "status": "Open"},
			pluck="allocated_to",
		))
		extra = [u for u in executives if u not in assigned]
		if extra:
			assign(task.name, task.subject, extra)
		frappe.get_doc("Task", task.name).add_comment("Comment", ESCALATED)
	frappe.db.commit()
