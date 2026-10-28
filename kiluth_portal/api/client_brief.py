"""Client briefs from kiluth.com/brief/: the AE fills one in with a client.

Called only by the kiluth.com form Lambda (kiluth-infra, POST /api/brief),
signed in as the website bot user, like website_lead. It writes and never
reads back: the one thing returned is the PDF of the brief just sent.

A brief is never filed on a project by the code typed on the form: a real code
for the wrong client would put it on someone else's project, and a first brief
often comes before there is a project at all. So it waits on a task for a
person to link (Poom, 2026-10-28):

  1. One task "Link client brief: <client>", shared out among Sales the way
     website leads are (utils/lead_routing.py: the least-busy salesperson).
     The project code from the form, if any, is only a hint in its description.
  2. Two private files on that task: the brief as a PDF in the Kiluth report
     design, and the raw answers as JSON for processing later.
  3. The AE sets the task's Project (or notes the Lead) and completes it. A
     second brief for the same client while the task is open lands on it too.

A brief sent from staging.kiluth.com (test=1) is filed the same way, marked
TEST in the file names, the task and the PDF.

  POST /api/method/kiluth_portal.api.client_brief.submit_client_brief
       client, project (a hint, optional), lang, summary (JSON), data (JSON), test
  response = {"pdf": "<base64>", "file": "client-brief-Baanploypoom-2026-10-28.pdf", "task": "TASK-…"}
"""

from __future__ import annotations

import base64
import json

import frappe

from kiluth_portal.api.website_lead import BOT_USER
from kiluth_portal.utils import brief_rules as br
from kiluth_portal.utils.lead_routing import assign, pick_salesperson

SUBJECT = "Link client brief: "


@frappe.whitelist(methods=["POST"])
def submit_client_brief(client=None, project=None, lang=None, summary=None, data=None, test=None):
	if frappe.session.user != BOT_USER:
		frappe.throw("Not allowed", frappe.PermissionError)

	client = br.clean_client(client)
	if not client:
		frappe.throw("A client name is required")
	try:
		lines = br.clean_summary(json.loads(summary or ""))
		answers = br.clean_data(json.loads(data or ""))
	except (ValueError, TypeError) as e:
		frappe.throw(f"Bad brief: {e}")

	is_test = str(test) == "1"
	hint = (project or "").strip().upper()
	hint = hint if br.PROJECT_RE.match(hint) else ""
	lang = "th" if lang == "th" else "en"
	meta = {"client": client, "project": hint, "lang": lang, "test": is_test, "by": br.field(answers, "by"), "date": br.field(answers, "date", 10)}

	from kiluth_portal.utils import report_pdf as rp

	pdf = rp.pdf(br.build_html(lines, meta, rp))
	task = _link_task(client, hint, is_test)
	base = br.file_base(client, meta["date"], is_test)
	pdf_file = _attach(task, f"{base}.pdf", pdf)
	_attach(task, f"{base}.json", json.dumps({"lang": lang, "summary": lines, "data": answers}, ensure_ascii=False, indent=1).encode())
	return {"pdf": base64.b64encode(pdf).decode(), "file": pdf_file.file_name, "task": task}


def _attach(task, name, content):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"attached_to_doctype": "Task",
			"attached_to_name": task,
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)


def _link_task(client, hint, is_test):
	subject = f"{SUBJECT}{'TEST · ' if is_test else ''}{client}"[:140]
	open_task = frappe.db.get_value("Task", {"subject": subject, "status": ["in", ["Open", "Working"]]}, "name")
	if open_task:
		frappe.get_doc("Task", open_task).add_comment("Comment", "Another brief arrived for this client: its files are attached below.")
		return open_task

	esc = frappe.utils.escape_html
	where = "<br><br>Sent from staging.kiluth.com as a test." if is_test else ""
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": "Open",
			"priority": "Medium",
			"department": "Account Management - K",
			"description": (
				f"A client brief for {esc(client)}, filled in at kiluth.com/brief (the Briefing Doc in the Client Onboarding Pack). "
				"The brief is attached as a PDF, with the answers as data beside it.<br><br>"
				+ (f"Project code typed on the form: {esc(hint)}. Check it before you link.<br><br>" if hint else "No project code was given.<br><br>")
				+ "<b>Done when</b> this task's Project is set to the client's project (or the Lead is named in a comment, "
				"when there is no project yet) and the brief has been checked with the client."
				+ where
			),
		}
	).insert(ignore_permissions=True)
	# Sales takes it in turn, like website leads (Poom, 2026-10-28).
	assign(task.name, task.subject, [pick_salesperson()])
	return task.name
