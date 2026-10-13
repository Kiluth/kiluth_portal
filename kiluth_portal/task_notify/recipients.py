"""Who gets notified for a Task event.

Pure functions only — no frappe import — so the oracle tests in
`kiluth_portal/tests/test_task_notify_recipients.py` run with plain `python -m
unittest`, no bench needed. `handlers.py` reads the docs and calls these.

The rules (from Poom, 2026-10-13):
1. Only the assignee is notified. Nobody else, ever.
2. You are never notified about your own action (self-assign, own comment).
3. A comment by someone else on a Task notifies that Task's assignee(s).
"""

import json

# Comment rows Frappe writes on a Task that are NOT a human comment: "Info",
# "Assigned", "Attachment", "Like", "Edit", ... Only real comments push.
NOTIFY_COMMENT_TYPES = frozenset({"Comment"})

TASK_DOCTYPE = "Task"


def _clean(user):
	return (user or "").strip()


def parse_assign(assign_json):
	"""Parse a doc's `_assign` field (JSON list of user ids) into a list."""
	if not assign_json:
		return []
	try:
		users = json.loads(assign_json)
	except (TypeError, ValueError):
		return []
	if not isinstance(users, list):
		return []
	return [u for u in (_clean(x) for x in users if isinstance(x, str)) if u]


def assignment_recipients(*, reference_type, allocated_to, actor, status, is_new, old_status=None):
	"""Recipients for a ToDo insert/update.

	Fires when a ToDo pointing at a Task becomes Open: a fresh insert, or a
	Cancelled/Closed ToDo re-opened (Frappe's assign_to reuses the old row when
	you re-assign the same person).
	"""
	if reference_type != TASK_DOCTYPE or status != "Open":
		return []
	if not is_new and old_status == "Open":
		return []
	assignee = _clean(allocated_to)
	if not assignee or assignee == _clean(actor):
		return []
	return [assignee]


def comment_recipients(*, reference_doctype, comment_type, commenter, task_assign_json):
	"""Recipients for a new Comment row: the Task's assignees minus the commenter."""
	if reference_doctype != TASK_DOCTYPE or comment_type not in NOTIFY_COMMENT_TYPES:
		return []
	commenter = _clean(commenter)
	return sorted({u for u in parse_assign(task_assign_json) if u != commenter})
