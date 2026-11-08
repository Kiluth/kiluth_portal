"""People-only notifications: who hears what when they asked to hear only from people.

Pure functions, no frappe import, so the oracle runs without a bench
(`kiluth_portal/tests/test_task_notify_quiet.py`).

Off for everyone until a user is listed in site_config (Poom, 2026-11-08,
TASK-2026-00151):
  "kiluth_people_only_notify": ["poom.pengcharoen@kiluth.com"]
  "kiluth_notify_bots": ["swarm@kiluth.com"]   (this list when unset)

For a listed user:
1. "Your assignment was removed" is never written.
2. Nothing from a bot (the swarm, the task check, the system) emails or pushes.
   The Notification Log row is still written, so Hub still reads it.
3. The phone buzzes only when a person assigns them a task, a person's comment
   mentions them, or for their own tasks due today (digest.py).
4. No email per notification. One daily summary instead (digest.py).
Everyone not listed keeps today's behaviour exactly.
"""

DEFAULT_BOTS = ("swarm@kiluth.com",)
# Rows Frappe writes with no person behind them.
SYSTEM_USERS = frozenset({"", "Administrator", "Guest"})

ASSIGNED = "task.assigned"
DUE = "task.due"
BELL = "bell"

# Frappe's own wording (frappe/desk/form/assign_to.py, notify_assignment, action CLOSE).
REMOVED_MARK = "has been removed by"


def _clean(user):
	return (user or "").strip()


def settings(conf):
	"""(people_only users, bots) from site_config. Both are sets."""
	people_only = {_clean(u) for u in (conf.get("kiluth_people_only_notify") or []) if _clean(u)}
	bots = {_clean(u) for u in (conf.get("kiluth_notify_bots") or DEFAULT_BOTS) if _clean(u)}
	return people_only, bots


def is_bot(user, bots):
	user = _clean(user)
	return user in SYSTEM_USERS or user in bots


# ─── Notification Log (the desk's bell and its emails) ──────────────────────

def drop_log(*, for_user, log_type, subject, people_only):
	"""True: don't write this Notification Log row at all (rule 1)."""
	return _clean(for_user) in people_only and log_type == "Assignment" and REMOVED_MARK in (subject or "")


def email_log(*, for_user, people_only):
	"""False: the row is written but sends no email of its own (rules 2 and 4)."""
	return _clean(for_user) not in people_only


def in_summary(*, log_type, from_user, subject, bots):
	"""True: the row goes in the daily summary email. People's assignments and mentions only."""
	if is_bot(from_user, bots):
		return False
	if log_type == "Assignment":
		return REMOVED_MARK not in (subject or "")
	return log_type == "Mention"


# ─── Task Notifications listener (phone push, log, bell) ────────────────────

def recipients(event, people_only):
	"""The event's recipients, plus listed users the comment mentions.

	A mention reaches a listed user even on a task they aren't assigned. Users
	not listed get no extra rows: Frappe already writes them a Mention row.
	"""
	told = list(event["recipients"])
	actor = _clean(event.get("actor"))
	for user in event.get("mentioned") or []:
		user = _clean(user)
		if user in people_only and user not in told and user != actor:
			told.append(user)
	return told


def allowed(channel, recipient, event, people_only, bots):
	"""Should this channel tell this recipient about this event?"""
	original = recipient in event["recipients"]
	if recipient not in people_only:
		return original
	if channel == BELL:
		# The in-app record Hub reads. Only for the rows it always had: a
		# mention already has Frappe's own Mention row.
		return original
	if event["event_type"] == DUE:
		return True
	if is_bot(event.get("actor"), bots) or event["payload"].get("from_check"):
		return False
	if event["event_type"] == ASSIGNED:
		return original
	return recipient in (event.get("mentioned") or [])
