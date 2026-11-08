"""People-only notifications (task_notify/quiet.py) on a LOCAL THROWAWAY bench.

Runs every job in-process (no worker needed). Creates made-up users and a
made-up Task. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_people_only.run

Not named test_*, so the Frappe test runner and the pure-Python oracle skip it.
"""

import frappe
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import getdate

from kiluth_portal.task_notify import digest, jobs
from kiluth_portal.task_notify.events import assignment_event, comment_event

QUIET = "e2e-quiet@kiluth.com"  # listed: people-only
LOUD = "e2e-loud@kiluth.com"  # not listed: today's behaviour
PERSON = "e2e-person@kiluth.com"
BOT = "e2e-bot@kiluth.com"
REMOVED = "Your assignment on <b>Task</b> <b>x</b> has been removed by <b>Bot</b>"


def _user(email, first_name):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0,
			"roles": [{"role": "Projects User"}]}).insert(ignore_permissions=True)


def _logs(user, mark):
	return frappe.get_all("Notification Log", filters={"for_user": user, "subject": ("like", f"%{mark}%")}, pluck="type")


def _mails(user, since):
	return frappe.db.count("Email Queue", {"creation": (">=", since), "name": ("in", frappe.get_all(
		"Email Queue Recipient", filters={"recipient": user}, pluck="parent") or [""])})


def _pushes(task):
	return sorted((r.recipient, r.channel, r.event_type) for r in frappe.get_all(
		jobs.DOCTYPE, filters={"task": task}, fields=["recipient", "channel", "event_type"]))


def run():
	for email, name in ((QUIET, "Quiet"), (LOUD, "Loud"), (PERSON, "Person"), (BOT, "Bot")):
		_user(email, name)
	frappe.local.conf["kiluth_people_only_notify"] = [QUIET]
	frappe.local.conf["kiluth_notify_bots"] = [BOT]
	frappe.local.conf["kiluth_notify_channels"] = ["log"]
	since = frappe.utils.now()
	mark = frappe.generate_hash(length=8)
	results = {}

	# 1. Removed: not written for QUIET, written for LOUD.
	make_notification_logs(frappe._dict(type="Assignment", subject=f"{REMOVED} {mark}", from_user=BOT,
		document_type="ToDo", document_name="x"), [QUIET, LOUD])
	results["removed_quiet"] = _logs(QUIET, mark) == []
	results["removed_loud"] = _logs(LOUD, mark) == ["Assignment"]

	# 2. Bot and person assignment rows: written for QUIET, no email; LOUD still emailed.
	for who in (BOT, PERSON):
		m = f"{mark}-{who}"
		make_notification_logs(frappe._dict(type="Assignment", subject=f"assigned you {m}", from_user=who,
			document_type="ToDo", document_name="x"), [QUIET, LOUD])
		results[f"row_kept_quiet_{who}"] = _logs(QUIET, m) == ["Assignment"]
	results["no_email_quiet"] = _mails(QUIET, since) == 0
	results["email_loud"] = _mails(LOUD, since) == 3

	# 3. Push: due task assigned to QUIET by a person, today.
	task = frappe.get_doc({"doctype": "Task", "subject": f"People-only {mark}", "exp_end_date": getdate(),
		"status": "Open"}).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "ToDo", "allocated_to": QUIET, "reference_type": "Task", "reference_name": task.name,
		"status": "Open", "assigned_by": PERSON, "description": "x"}).db_insert()
	for actor in (BOT, PERSON):
		jobs.process(assignment_event(todo=f"t-{actor}-{mark}", reference_type="Task", task=task.name, task_subject=task.subject,
			allocated_to=QUIET, actor=actor, actor_name=actor, status="Open", is_new=True, old_status=None, modified="m"))
	jobs.process(comment_event(comment=f"c1-{mark}", reference_doctype="Task", task=task.name, task_subject=task.subject,
		comment_type="Comment", commenter=PERSON, commenter_name="Person", text="no mention",
		task_assign_json=f'["{QUIET}"]'))
	jobs.process(comment_event(comment=f"c2-{mark}", reference_doctype="Task", task=task.name, task_subject=task.subject,
		comment_type="Comment", commenter=PERSON, commenter_name="Person", text="hey",
		task_assign_json=f'["{QUIET}"]', mentioned=[QUIET]))
	before_digest = _pushes(task.name)
	results["push_person_only"] = before_digest == sorted([
		(QUIET, "bell", "task.assigned"), (QUIET, "bell", "task.assigned"),  # bell rows kept (they no-op for assignments)
		(QUIET, "bell", "task.commented"), (QUIET, "bell", "task.commented"),
		(QUIET, "log", "task.assigned"),  # person assigns
		(QUIET, "log", "task.commented"),  # person mentions
	])

	# 4. Daily summary: one email, one due push; the same day again adds no push.
	# (Frappe also drops the identical second email inside one process.)
	sent = digest.send_daily(only=QUIET)
	digest.send_daily(only=QUIET)
	results["digest_sent"] = sent == [QUIET]
	results["digest_one_due_push"] = [p for p in _pushes(task.name) if p[2] == "task.due"] == [(QUIET, "log", "task.due")]
	results["digest_emails"] = _mails(QUIET, since) == 1

	frappe.db.rollback()
	for k, v in results.items():
		print(("PASS" if v else "FAIL"), k)
	if not all(results.values()):
		print("after:", _pushes(task.name))
		print("pushes:", before_digest)
	return all(results.values())
