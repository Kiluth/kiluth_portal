"""Weekly holiday email: the days off in the coming week, in the Kiluth design.

Replaces HRMS's "Upcoming Holidays Reminder" (Poom, 2026-10-27), whose subject
and wording are fixed in HRMS code. HR Settings `send_holiday_reminders` is
turned off by patches/v2026/own_holiday_reminder.py so only this one sends.

Every Monday 08:00 (Asia/Bangkok), each active employee with a holiday from
Monday to Sunday gets one email. Same holidays and holiday list as HRMS used
(`get_holidays_for_employee`, weekly offs left out). The look is the shared
report email (utils/report_email.py) with the amber-leaf photo.

Manual run (System Manager), sends only to the given address:

    bench --site portal.kiluth.com execute \
        kiluth_portal.kiluth_hr.holiday_reminder.send_weekly --kwargs "{'only': 'poom.pengcharoen@kiluth.com'}"

The wording part imports nothing from Frappe, so tests run it without a bench.
"""

from __future__ import annotations

import datetime as dt

HERO = "hero-holiday.jpg"


def _day(d: dt.date) -> str:
	return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def _week(start: dt.date, end: dt.date) -> str:
	if start.month == end.month:
		return f"{start.day}–{end.day} {end.strftime('%B %Y')}"
	return f"{start.day} {start.strftime('%B')} – {end.day} {end.strftime('%B %Y')}"


def wording(first_name: str, holidays: list, start: dt.date, end: dt.date) -> dict:
	"""holidays: [(date, description)], sorted. Returns subject, title, kicker, lines."""
	n = len(holidays)
	if n == 1:
		d, what = holidays[0]
		subject = f"Day off on {_day(d)}: {what}"
		title = "A day off this week"
	else:
		subject = f"{n} days off this week"
		title = f"{n} days off this week"
	lines = [f"Hi {first_name}," if first_name else "Hi,"]
	lines += [f"**{_day(d)}**: {what}." for d, what in holidays]
	lines.append("Enjoy the time off.")
	return {"subject": subject, "title": title, "kicker": _week(start, end), "lines": lines}


# ─── Portal side ─────────────────────────────────────────────────────────────

def send_weekly(only: str | None = None):
	"""Scheduler job. `only`: send just to this address (manual test)."""
	import frappe
	from erpnext.setup.doctype.employee.employee import get_employee_email
	from frappe.utils import add_days, get_url, getdate, strip_html
	from hrms.hr.utils import get_holidays_for_employee

	from kiluth_portal.utils.report_email import email_html

	start = getdate()
	end = add_days(start, 6)
	sent = []
	for name in frappe.get_all("Employee", filters={"status": "Active"}, pluck="name"):
		holidays = get_holidays_for_employee(name, start, end, only_non_weekly=True, raise_exception=False)
		if not holidays:
			continue
		emp = frappe.get_doc("Employee", name)
		to = get_employee_email(emp)
		if not to or (only and to.lower() != only.lower()):
			continue
		w = wording(emp.first_name or "", [(getdate(h.holiday_date), strip_html(h.description or "").strip()) for h in holidays], start, end)
		frappe.sendmail(
			recipients=[to],
			subject=w["subject"],
			message=email_html(title=w["title"], kicker=w["kicker"], lines=w["lines"], hero=HERO,
				assets=get_url("/assets/kiluth_portal/"), portal_url=get_url(), sign_off="— Kiluth"),
			delayed=False,
		)
		sent.append(to)
	return sent
