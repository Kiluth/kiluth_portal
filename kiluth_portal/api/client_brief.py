"""Client briefs from kiluth.com/brief/: the AE fills one in with a client.

Called only by the kiluth.com form Lambda (kiluth-infra, POST /api/brief),
signed in as the website bot user, like website_lead. It writes and never
reads back: the one thing returned is the PDF of the brief just sent.

  1. The project must exist and be open; anything else is DoesNotExistError (404).
  2. Two private files go on the project: the brief as a PDF in the Kiluth report
     design, and the raw answers as JSON for processing later.
  3. A comment on the project links both.
  4. One task "Review client brief: PROJ-…" for the project's AE (the Account
     Manager on the project, else the customer's), who owns the brief at kickoff
     (docs.kiluth.com/delivery/delivery-and-resourcing). A second brief while it
     is open adds a comment there instead of a second task.

A brief sent from staging.kiluth.com (test=1) is filed the same way, marked
TEST in the file names, the comment and the PDF.

  POST /api/method/kiluth_portal.api.client_brief.submit_client_brief
       project, lang, summary (JSON), data (JSON), test
  response = {"pdf": "<base64>", "file": "client-brief-PROJ-0015-2026-10-28.pdf", "task": "TASK-…"}
"""

from __future__ import annotations

import base64
import json

import frappe

from kiluth_portal.api.website_lead import BOT_USER
from kiluth_portal.utils import brief_rules as br
from kiluth_portal.utils.lead_routing import account_manager, assign

SUBJECT = "Review client brief: "
CLOSED = ("Completed", "Cancelled")


@frappe.whitelist(methods=["POST"])
def submit_client_brief(project=None, lang=None, summary=None, data=None, test=None):
	if frappe.session.user != BOT_USER:
		frappe.throw("Not allowed", frappe.PermissionError)

	project = (project or "").strip().upper()
	info = frappe.db.get_value("Project", project, ["status", "customer", "account_manager"], as_dict=True) if br.PROJECT_RE.match(project) else None
	if not info or info.status in CLOSED:
		frappe.throw("Unknown project", frappe.DoesNotExistError)

	try:
		lines = br.clean_summary(json.loads(summary or ""))
		answers = br.clean_data(json.loads(data or ""))
	except (ValueError, TypeError) as e:
		frappe.throw(f"Bad brief: {e}")

	is_test = str(test) == "1"
	lang = "th" if lang == "th" else "en"
	meta = {"project": project, "lang": lang, "test": is_test, "client": br.field(answers, "client"), "by": br.field(answers, "by"), "date": br.field(answers, "date", 10)}

	from kiluth_portal.utils import report_pdf as rp

	pdf = rp.pdf(br.build_html(lines, meta, rp))
	base = br.file_base(project, meta["date"], is_test)
	pdf_file = _attach(project, f"{base}.pdf", pdf)
	json_file = _attach(project, f"{base}.json", json.dumps({"lang": lang, "summary": lines, "data": answers}, ensure_ascii=False, indent=1).encode())

	where = " (a test from staging.kiluth.com)" if is_test else ""
	frappe.get_doc("Project", project).add_comment(
		"Comment",
		f"Client brief from kiluth.com/brief{where}: "
		f'<a href="{pdf_file.file_url}">{frappe.utils.escape_html(pdf_file.file_name)}</a>, '
		f'and the answers as data: <a href="{json_file.file_url}">{frappe.utils.escape_html(json_file.file_name)}</a>.',
	)
	task = _review_task(project, info, pdf_file.file_name)
	return {"pdf": base64.b64encode(pdf).decode(), "file": pdf_file.file_name, "task": task}


def _attach(project, name, content):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"attached_to_doctype": "Project",
			"attached_to_name": project,
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)


def _review_task(project, info, file_name):
	subject = f"{SUBJECT}{project}"
	open_task = frappe.db.get_value("Task", {"subject": subject, "status": ["in", ["Open", "Working"]]}, "name")
	if open_task:
		frappe.get_doc("Task", open_task).add_comment("Comment", f"Another client brief arrived: {frappe.utils.escape_html(file_name)}, on the project.")
		return open_task

	link = frappe.utils.get_url_to_form("Project", project)
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": project,
			"status": "Open",
			"priority": "Medium",
			"department": "Account Management - K",
			"description": (
				f'Project link: <a href="{link}">{project}</a><br>'
				f"The brief is attached to the project as {frappe.utils.escape_html(file_name)}, with the answers as data beside it.<br><br>"
				"Filled in with the client at kiluth.com/brief (the Briefing Doc in the Client Onboarding Pack).<br><br>"
				"<b>Done when</b> the AE has checked the brief with the client and linked its sign-off proof on the project, "
				"as kickoff asks (Delivery and Resourcing)."
			),
		}
	).insert(ignore_permissions=True)
	am = info.account_manager if info.account_manager and frappe.db.get_value("User", info.account_manager, "enabled") else None
	assign(task.name, task.subject, [am or account_manager(info.customer)])
	return task.name
