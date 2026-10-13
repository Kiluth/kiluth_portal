"""doc_events glue: read the docs, ask recipients.py who to tell, queue the send.

Sending happens in a background job after commit so a slow push service never
blocks saving a Task, and a rolled-back save never pushes.
"""

import frappe

from kiluth_portal.web_push.recipients import assignment_recipients, comment_recipients


def _queue(users, payload):
	if not users:
		return
	frappe.enqueue(
		"kiluth_portal.web_push.sender.send_to_users",
		users=users,
		payload=payload,
		queue="short",
		enqueue_after_commit=True,
	)


def _task_url(task):
	return f"/app/task/{task}"


def _task_subject(task):
	return frappe.db.get_value("Task", task, "subject") or task


def on_todo_change(doc, method=None):
	# Hooked on on_update only: Frappe runs on_update after after_insert too, so
	# hooking both would push twice. No doc-before-save means this is the insert.
	before = doc.get_doc_before_save()
	users = assignment_recipients(
		reference_type=doc.reference_type,
		allocated_to=doc.allocated_to,
		actor=doc.assigned_by or frappe.session.user,
		status=doc.status,
		is_new=before is None,
		old_status=before.status if before else None,
	)
	if not users:
		return
	actor = frappe.utils.get_fullname(doc.assigned_by or frappe.session.user)
	_queue(
		users,
		{
			"title": f"{actor} assigned you a task",
			"body": _task_subject(doc.reference_name),
			"url": _task_url(doc.reference_name),
			"tag": f"task-{doc.reference_name}",
		},
	)


def on_comment_insert(doc, method=None):
	if doc.reference_doctype != "Task":
		return
	commenter = doc.comment_email or doc.owner
	users = comment_recipients(
		reference_doctype=doc.reference_doctype,
		comment_type=doc.comment_type,
		commenter=commenter,
		task_assign_json=frappe.db.get_value("Task", doc.reference_name, "_assign"),
	)
	if not users:
		return
	text = frappe.utils.strip_html(doc.content or "").strip()
	_queue(
		users,
		{
			"title": f"{frappe.utils.get_fullname(commenter)} on {_task_subject(doc.reference_name)}",
			"body": text[:180],
			"url": _task_url(doc.reference_name),
			"tag": f"task-{doc.reference_name}",
		},
	)
