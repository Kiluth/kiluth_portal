"""Turn a ToDo or Comment save into one notification event.

Pure functions, no frappe import, so the oracle runs without a bench.

An event is a plain dict (it has to survive the trip through the RQ queue):
  event_id    stable id; the same save seen twice gives the same id
  event_type  "task.assigned" | "task.commented"
  task        Task name
  actor       user who did it (never a recipient)
  recipients  users to tell, from recipients.py
  payload     what any channel needs to show it: title, body, url, tag, task
"""

from kiluth_portal.task_notify.recipients import assignment_recipients, comment_recipients

ASSIGNED = "task.assigned"
COMMENTED = "task.commented"
BODY_LIMIT = 180


def _payload(*, title, body, task):
	return {
		"title": title,
		"body": body,
		"url": f"/app/task/{task}",
		"tag": f"task-{task}",
		"task": task,
	}


def assignment_event(*, todo, reference_type, task, task_subject, allocated_to, actor, actor_name, status, is_new, old_status, modified):
	"""Event for a ToDo insert/update, or None if nobody should hear about it.

	`modified` is the ToDo's modified timestamp. It makes the id stable for one
	save (a hook firing twice) but new for a later re-assignment of the same row.
	"""
	recipients = assignment_recipients(
		reference_type=reference_type,
		allocated_to=allocated_to,
		actor=actor,
		status=status,
		is_new=is_new,
		old_status=old_status,
	)
	if not recipients:
		return None
	return {
		"event_id": f"todo:{todo}:{modified}",
		"event_type": ASSIGNED,
		"task": task,
		"actor": actor,
		"recipients": recipients,
		"payload": _payload(title=f"{actor_name} assigned you a task", body=task_subject or task, task=task),
	}


def comment_event(*, comment, reference_doctype, task, task_subject, comment_type, commenter, commenter_name, text, task_assign_json):
	"""Event for a new Comment row, or None. A Comment is inserted once, so its name is the id."""
	recipients = comment_recipients(
		reference_doctype=reference_doctype,
		comment_type=comment_type,
		commenter=commenter,
		task_assign_json=task_assign_json,
	)
	if not recipients:
		return None
	return {
		"event_id": f"comment:{comment}",
		"event_type": COMMENTED,
		"task": task,
		"actor": commenter,
		"recipients": recipients,
		"payload": _payload(
			title=f"{commenter_name} on {task_subject or task}",
			body=(text or "").strip()[:BODY_LIMIT],
			task=task,
		),
	}
