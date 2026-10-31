"""Task Waterfall: each project's tasks in the order their dependencies set.

Dates play no part, because most open tasks have none (Poom, 2026-10-31). The
order comes from Dependent Tasks; see utils/task_chain.py.
"""

import json

import frappe

from kiluth_portal.utils.task_chain import layout, through_hidden

FINISHED = ("Completed", "Cancelled")
OPERATIONS = "PROJ-0001"


@frappe.whitelist()
def get_data(show_finished=0):
	"""Every task this user can read, grouped by project. get_list keeps Task permissions."""
	show_finished = frappe.utils.cint(show_finished)
	rows = frappe.get_list(
		"Task",
		fields=["name", "subject", "status", "project", "_assign"],
		filters=[["status", "!=", "Template"]],
		order_by="name asc",
		limit_page_length=0,
	)
	links_of = frappe.get_all(
		"Task Depends On",
		filters={"parenttype": "Task", "parent": ["in", [r.name for r in rows] or [""]]},
		fields=["parent", "task"],
	)
	readable = {r.name for r in rows}
	links = [(l.task, l.parent) for l in links_of if l.task in readable]

	by_project = {}
	for r in rows:
		by_project.setdefault(r.project or "", []).append(r)

	titles = dict(frappe.get_all("Project", fields=["name", "project_name"], as_list=True))
	out = []
	for project, tasks in by_project.items():
		shown = [t for t in tasks if show_finished or t.status not in FINISHED]
		if not shown:
			continue
		names = [t.name for t in shown]
		inside = {t.name for t in tasks}
		placed = layout(names, through_hidden(names, [(a, b) for a, b in links if a in inside and b in inside]))
		out.append({
			"project": project,
			"title": titles.get(project) or "",
			"tasks": {
				t.name: {
					"subject": t.subject,
					"status": t.status,
					"assignees": json.loads(t._assign or "[]"),
				}
				for t in shown
			},
			**placed,
		})
	# Client work first, newest project on top; Operations and "no project" after it.
	out.sort(key=lambda p: (p["project"] in (OPERATIONS, ""), p["project"] == "", [-ord(c) for c in p["project"]]))
	people = {a for p in out for t in p["tasks"].values() for a in t["assignees"]}
	names = dict(frappe.get_all("User", filters={"name": ["in", list(people) or [""]]}, fields=["name", "full_name"], as_list=True))
	return {"projects": out, "people": names, "me": frappe.session.user}
