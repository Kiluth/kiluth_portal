"""doc_events glue: read the doc, build the event, queue it. Nothing else.

Each hook is `guarded`, so an error here is logged and the save goes on.
The job is queued after commit: a rolled-back save never notifies anyone.
"""

import frappe

from kiluth_portal.task_notify.dispatch import guarded
from kiluth_portal.task_notify.events import assignment_event, comment_event


def _enqueue(event):
	if not event:
		return
	frappe.enqueue(
		"kiluth_portal.task_notify.jobs.process",
		event=event,
		queue="short",
		enqueue_after_commit=True,
	)


def _subject(task):
	return frappe.db.get_value("Task", task, "subject") if task else None


@guarded
def on_todo_change(doc, method=None):
	# on_update only: Frappe runs on_update after after_insert too, so hooking
	# both would queue twice. No doc-before-save means this save is the insert.
	before = doc.get_doc_before_save()
	actor = doc.assigned_by or frappe.session.user
	_enqueue(
		assignment_event(
			todo=doc.name,
			reference_type=doc.reference_type,
			task=doc.reference_name,
			task_subject=_subject(doc.reference_name) if doc.reference_type == "Task" else None,
			allocated_to=doc.allocated_to,
			actor=actor,
			actor_name=frappe.utils.get_fullname(actor),
			status=doc.status,
			is_new=before is None,
			old_status=before.status if before else None,
			modified=str(doc.modified),
		)
	)


@guarded
def on_comment_insert(doc, method=None):
	if doc.reference_doctype != "Task":
		return
	commenter = doc.comment_email or doc.owner
	_enqueue(
		comment_event(
			comment=doc.name,
			reference_doctype=doc.reference_doctype,
			task=doc.reference_name,
			task_subject=_subject(doc.reference_name),
			comment_type=doc.comment_type,
			commenter=commenter,
			commenter_name=frappe.utils.get_fullname(commenter),
			text=frappe.utils.strip_html(doc.content or ""),
			task_assign_json=frappe.db.get_value("Task", doc.reference_name, "_assign"),
		)
	)
