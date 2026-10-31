"""When the task check runs. The one place to change that.

Poom's list (2026-10-31): a task is created, or its title, description,
dependencies or assignee change. Comments, attachments, status and every other
save start nothing, and that is also what stops the checker triggering itself:
it writes only `hygiene` and `hygiene_note`, which are not on this list.

No Frappe here, so the list can be tested on its own:

	python3 kiluth_portal/tests/test_task_check_triggers.py
"""

from __future__ import annotations

TASK_FIELDS = ("subject", "description", "depends_on")
ASSIGNEE = True


def task_state(doc) -> dict:
	"""The parts of a Task the list above looks at. `doc` is a Task document."""
	state = {f: doc.get(f) for f in TASK_FIELDS if f != "depends_on"}
	if "depends_on" in TASK_FIELDS:
		state["depends_on"] = sorted(d.task for d in doc.get("depends_on") or [])
	return state


def task_changed(before: dict | None, after: dict) -> bool:
	"""Does this save start a run? No `before` means the task is new."""
	if before is None:
		return True
	return any((before.get(f) or None) != (after.get(f) or None) for f in TASK_FIELDS)


def assignee_changed(reference_type: str, before_status: str | None, status: str) -> bool:
	"""Does this ToDo save change who is on a Task?

	A ToDo is one person's assignment: a new one adds a name, and leaving or
	re-entering Open takes one off or puts it back. Assignments never save the
	Task itself, so this is the only place they show up.
	"""
	if not ASSIGNEE or reference_type != "Task":
		return False
	return before_status is None or (before_status == "Open") != (status == "Open")
