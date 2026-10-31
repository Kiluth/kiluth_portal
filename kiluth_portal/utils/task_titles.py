"""Titles of tasks on PROJ-0001 Operations start with their department.

"[Finance] Close the books for October 2026" (Poom, 2026-11-01). Client project
tasks don't carry one.

Jobs here find their own tasks by title, so a title with the prefix and one
without have to count as the same task, or the job makes a second one. Find
through `same_title`; never compare a subject directly.
"""

from __future__ import annotations

import re

_PREFIX = re.compile(r"^\[[^\]]*\]\s*")


def bare(subject: str | None) -> str:
	"""The title without its [Department] prefix."""
	return _PREFIX.sub("", subject or "")


def with_department(subject: str, department: str | None) -> str:
	"""The title for an Operations task. `department` is a Department record, "Finance - K"."""
	name = (department or "").removesuffix(" - K").strip()
	return f"[{name}] {bare(subject)}" if name else subject


def same_title(subject: str, filters: dict | None = None) -> list[str]:
	"""Names of Tasks titled `subject`, with or without a [Department] prefix."""
	import frappe

	rows = frappe.get_all(
		"Task",
		filters={**(filters or {}), "subject": ["like", f"%{bare(subject)}"]},
		fields=["name", "subject"],
	)
	return [r.name for r in rows if bare(r.subject) == bare(subject)]
