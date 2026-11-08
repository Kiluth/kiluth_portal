"""The daily summary for people-only users (quiet.py), 08:00 Asia/Bangkok.

For each user in `kiluth_people_only_notify`:
  - one push per open task of theirs due today
  - one email: people who assigned them a task or mentioned them in the last
    24 hours, and what's due today. No email when there's nothing.
Swarm and task check items are left out: Hub handles those.

Manual run (System Manager), sends only to the given address:

    bench --site portal.kiluth.com execute \
        kiluth_portal.task_notify.digest.send_daily --kwargs "{'only': 'poom.pengcharoen@kiluth.com'}"

The wording part imports nothing from Frappe, so tests run it without a bench.
"""

from __future__ import annotations

HERO = "hero-leaf-lit.jpg"
DUE = "task.due"
CLOSED = ("Completed", "Cancelled", "Template")


def wording(first_name: str, people: list[str], due: list[str], day: str) -> dict | None:
	"""people: one line per notification from a person. due: subjects due today.
	Returns subject, title, kicker, lines; None when there's nothing to say."""
	if not people and not due:
		return None
	parts = []
	if people:
		parts.append(f"{len(people)} from people" if len(people) > 1 else "1 from a person")
	if due:
		parts.append(f"{len(due)} due today")
	lines = [f"Hi {first_name}," if first_name else "Hi,"]
	if people:
		lines.append("**From people since yesterday:**")
		lines += people
	if due:
		lines.append("**Due today:**")
		lines += due
	return {"subject": f"Your Kiluth Tasks: {', '.join(parts)}", "title": "Your day in Kiluth Tasks", "kicker": day, "lines": lines}


def due_event(*, user, task, subject, day):
	"""One push for one task due today. The id holds the day, so a re-run the same day sends nothing new."""
	return {
		"event_id": f"due:{task}:{day}",
		"event_type": DUE,
		"task": task,
		"actor": user,
		"recipients": [user],
		"payload": {
			"title": "Due today",
			"body": subject or task,
			"url": f"/app/task/{task}",
			"tag": f"task-{task}",
			"task": task,
			"kind": DUE,
		},
	}


# ─── Portal side ─────────────────────────────────────────────────────────────

def _due_tasks(user, today):
	import frappe

	names = frappe.get_all(
		"ToDo",
		filters={"allocated_to": user, "status": "Open", "reference_type": "Task"},
		pluck="reference_name",
	)
	if not names:
		return []
	return frappe.get_all(
		"Task",
		filters={"name": ("in", list(set(names))), "exp_end_date": today, "status": ("not in", CLOSED)},
		fields=["name", "subject"],
		order_by="name asc",
	)


def _from_people(user, since, bots):
	import frappe
	from frappe.utils import strip_html

	from kiluth_portal.task_notify import quiet

	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": user, "creation": (">", since)},
		fields=["type", "from_user", "subject"],
		order_by="creation asc",
	)
	return [
		" ".join(strip_html(r.subject or "").split()) + "."
		for r in rows
		if quiet.in_summary(log_type=r.type, from_user=r.from_user, subject=r.subject, bots=bots)
	]


def send_daily(only: str | None = None):
	"""Scheduler job. `only`: just this address (manual test). Returns who got an email."""
	import frappe
	from frappe.utils import add_to_date, get_url, getdate, now_datetime

	from kiluth_portal.task_notify import channels, dispatch, quiet
	from kiluth_portal.task_notify.jobs import FrappeStore
	from kiluth_portal.utils.report_email import email_html

	people_only, bots = quiet.settings(frappe.conf)
	today = getdate()
	day = f"{today.strftime('%A')} {today.day} {today.strftime('%B %Y')}"
	since = add_to_date(now_datetime(), hours=-24)
	# The push half: the site's channels minus the bell (a due task is no comment).
	push = [c for c in channels.enabled(frappe.conf.get("kiluth_notify_channels")) if c.name != quiet.BELL]
	sent = []
	for user in sorted(people_only):
		if only and user.lower() != only.lower():
			continue
		due = _due_tasks(user, today)
		for t in due:
			dispatch.process_event(due_event(user=user, task=t.name, subject=t.subject, day=str(today)), FrappeStore(), push)
		w = wording(
			frappe.db.get_value("User", user, "first_name") or "",
			_from_people(user, since, bots),
			[f"{t.subject} ({t.name})." for t in due],
			day,
		)
		if not w:
			continue
		frappe.sendmail(
			recipients=[user],
			subject=w["subject"],
			message=email_html(title=w["title"], kicker=w["kicker"], lines=w["lines"], hero=HERO,
				assets=get_url("/assets/kiluth_portal/"), portal_url=get_url(),
				button="Open my tasks", href=get_url("/my-tasks"),
				why="You get this instead of one email per notification."),
			delayed=False,
		)
		sent.append(user)
	return sent
