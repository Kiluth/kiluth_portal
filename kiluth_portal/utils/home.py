"""Home: land people on the Task list, filtered to tasks assigned to them.

`/my-board` does the same for the Task Board.

`/my-tasks` is one stable address for "my Task list". It redirects a signed-in
user to `/desk/task?_assign=[like, %<user>%]`, which the desk list view reads as
an "Assigned To" filter. Sign-in, the site root, the phone app's start page and
old `/welcome` bookmarks all point here, so the per-user filter is worked out in
one place, after the user is known.

The links that used to live on the `/welcome` tile page are added to the
Projects sidebar, the one the Task list shows (`add_kiluth_sidebar_links`).
"""

import json
from urllib.parse import quote

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.utils import redirect

HOME_PATH = "my-tasks"
HOME_URL = "/" + HOME_PATH

SIDEBAR = "Projects"
SECTION_LABEL = "Kiluth"
BOARD = "Tasks"
BOARD_PATH = "my-board"
BOARD_URL = "/desk/task/view/kanban/" + BOARD
BOARD_COLUMNS = ("Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled")
SIDEBAR_LINKS = [
	{"label": "My Board", "link_type": "URL", "url": "/" + BOARD_PATH, "icon": "columns-3"},
	{"label": "Task Board", "link_type": "URL", "url": BOARD_URL, "icon": "columns-3"},
	{"label": "Task Waterfall", "link_type": "URL", "url": "/desk/task-waterfall", "icon": "network"},
	{"label": "Request Leave", "link_type": "URL", "url": "/request-leave", "icon": "calendar"},
	{"label": "Expense Claim", "link_type": "DocType", "link_to": "Expense Claim", "icon": "receipt"},
	{"label": "Timesheet Form", "link_type": "URL", "url": "/timesheet", "icon": "calendar-clock"},
	{"label": "Kiluth Docs", "link_type": "URL", "url": "https://docs.kiluth.com/", "icon": "book-open"},
	{"label": "Shared Drive", "link_type": "URL", "url": "https://drive.google.com/drive/u/1/shared-drives", "icon": "folder"},
]


def _assigned_to(user):
	value = json.dumps(["like", f"%{user}%"], separators=(",", ":"))
	return "_assign=" + quote(value, safe="")


def task_list_url(user):
	"""The desk Task list, filtered to tasks assigned to `user`."""
	return "/desk/task?" + _assigned_to(user)


def task_board_url(user):
	"""The Task Board, filtered to tasks assigned to `user`."""
	return BOARD_URL + "?" + _assigned_to(user)


class MyTasksRedirect(BaseRenderer):
	TARGETS = {HOME_PATH: task_list_url, BOARD_PATH: task_board_url}

	def can_render(self):
		return self.path in self.TARGETS

	def render(self):
		if frappe.session.user == "Guest":
			return redirect("/login?redirect-to=" + quote("/" + self.path, safe=""), 302)
		return redirect(self.TARGETS[self.path](frappe.session.user), 302)


def ensure_task_board():
	"""The Task Board: a card per task, in a column per status.

	Made once, here rather than as a fixture, so a later migrate never undoes
	what people change on the board.
	"""
	if frappe.db.exists("Kanban Board", BOARD):
		return
	frappe.get_doc(
		{
			"doctype": "Kanban Board",
			"kanban_board_name": BOARD,
			"reference_doctype": "Task",
			"field_name": "status",
			"fields": '["project"]',
			"show_labels": 0,
			"columns": [{"column_name": c} for c in BOARD_COLUMNS],
		}
	).insert(ignore_permissions=True)


def add_kiluth_sidebar_links():
	"""Append a "Kiluth" section with the old tile links to the Projects sidebar.

	The sidebar is a standard ERPNext record; a version bump can re-sync it and
	drop our rows. Running after every migrate puts them back. Adds missing rows
	only, never duplicates.
	"""
	if not frappe.db.exists("Workspace Sidebar", SIDEBAR):
		return
	sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR)
	labels = {row.label for row in sidebar.items}
	missing = [link for link in SIDEBAR_LINKS if link["label"] not in labels]
	if not missing:
		return
	if SECTION_LABEL not in labels:
		sidebar.append(
			"items",
			{"type": "Section Break", "label": SECTION_LABEL, "icon": "star", "indent": 1, "collapsible": 1},
		)
	for link in missing:
		sidebar.append("items", {"type": "Link", "child": 1, **link})
	sidebar.save(ignore_permissions=True)
