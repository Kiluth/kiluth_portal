"""Home: land people on the Task list, filtered to tasks assigned to them.

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
SIDEBAR_LINKS = [
	{"label": "Request Leave", "link_type": "URL", "url": "/request-leave", "icon": "calendar"},
	{"label": "Expense Claim", "link_type": "DocType", "link_to": "Expense Claim", "icon": "receipt"},
	{"label": "Timesheet Form", "link_type": "URL", "url": "/timesheet", "icon": "calendar-clock"},
	{"label": "Kiluth Docs", "link_type": "URL", "url": "https://docs.kiluth.com/", "icon": "book-open"},
	{"label": "Shared Drive", "link_type": "URL", "url": "https://drive.google.com/drive/u/1/shared-drives", "icon": "folder"},
]


def task_list_url(user):
	"""The desk Task list, filtered to tasks assigned to `user`."""
	value = json.dumps(["like", f"%{user}%"], separators=(",", ":"))
	return "/desk/task?_assign=" + quote(value, safe="")


class MyTasksRedirect(BaseRenderer):
	def can_render(self):
		return self.path == HOME_PATH

	def render(self):
		if frappe.session.user == "Guest":
			return redirect("/login?redirect-to=" + quote(HOME_URL, safe=""), 302)
		return redirect(task_list_url(frappe.session.user), 302)


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
