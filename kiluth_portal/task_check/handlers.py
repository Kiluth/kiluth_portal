"""doc_events glue for the task check: mark the task, queue one job. Nothing else.

The check itself runs outside the Portal (kiluth-infra modules/task-check). A
save on the list in triggers.py does two things:

  - clears the verdict in the same transaction, so a task only ever shows Pass
    or Fail for what the checker actually read. If the message below is lost,
    the task stays "not checked", and the daily run picks it up.
  - queues a job, after commit, that tells AWS (jobs.py).

Off until `task_check_queue_url` is in site_config: removing it is the off
switch, and needs no deploy. Each hook is `guarded`, so an error here is logged
and the save goes on.
"""

import frappe

from kiluth_portal.task_check import triggers
from kiluth_portal.task_notify.dispatch import guarded

NOT_CHECKED = "Not checked yet."


def _run_for(task):
	frappe.db.set_value("Task", task, {"hygiene": "", "hygiene_note": NOT_CHECKED}, update_modified=False)
	frappe.enqueue(
		"kiluth_portal.task_check.jobs.send",
		task=task,
		queue="short",
		enqueue_after_commit=True,
	)


@guarded
def on_task_update(doc, method=None):
	# on_update only: Frappe runs it after after_insert too. No doc-before-save
	# means this save is the insert.
	if not frappe.conf.get("task_check_queue_url"):
		return
	before = doc.get_doc_before_save()
	if triggers.task_changed(triggers.task_state(before) if before else None, triggers.task_state(doc)):
		_run_for(doc.name)


@guarded
def on_todo_change(doc, method=None):
	if not frappe.conf.get("task_check_queue_url"):
		return
	before = doc.get_doc_before_save()
	if triggers.assignee_changed(doc.reference_type, before.status if before else None, doc.status):
		_run_for(doc.reference_name)
