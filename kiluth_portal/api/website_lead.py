"""Website enquiries from the kiluth.com contact form.

Called only by the kiluth.com form Lambda (kiluth-infra), signed in as the
website bot user. That user has no roles and no doctype permissions: this one
method is all its API key can do.

Follows Lead Intake (docs.kiluth.com/marketing/lead-intake):
  1. the Lead holds the person's details (UTM Source "Website", Unqualified);
  2. one task "Qualify lead: <id>" holds only the link, assigned to the
     least-busy salesperson (utils/lead_routing.py: the "Sales" role).
The assignment email is how Sales hears about it.

Two optional extras (Poom, 2026-10-25):
  - heard: how they heard about Kiluth (one of HEARD), kept as the Lead's
    UTM Medium so Marketing can see which channels bring clients;
  - ref: a salesperson's Portal username from their planner link
    (kiluth.com/plan/?ref=<username>). One that belongs to an enabled user with
    the Sales role sends the task to that person; anything else is ignored and
    the lead is routed as usual.
A repeat enquiry from the same email adds a note to the lead and, if its
"Qualify lead" task is still open, a comment there instead of a second task.

  POST /api/method/kiluth_portal.api.website_lead.create_website_lead
       name, email, company, message, heard, ref (all but name and email optional)
  response = {"lead": "CRM-LEAD-2026-00042"}
"""

from __future__ import annotations

import re

import frappe

from kiluth_portal.utils.lead_routing import SUBJECT_PREFIX, assign, pick_salesperson, referred_salesperson

BOT_USER = "website-bot@kiluth.com"
SOURCE = "Website"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# What the website form sends → the UTM Medium it is filed under.
HEARD = {
	"search": "Search",
	"social": "Social media",
	"friend": "Friend or client",
	"kiluth": "Someone from Kiluth",
	"other": "Other",
}


def _clean(value, limit: int) -> str:
	return (value or "").strip()[:limit]


@frappe.whitelist(methods=["POST"])
def create_website_lead(name=None, email=None, company=None, message=None, heard=None, ref=None):
	if frappe.session.user != BOT_USER:
		frappe.throw("Not allowed", frappe.PermissionError)

	name = _clean(name, 140)
	email = _clean(email, 254).lower()
	company = _clean(company, 140)
	message = _clean(message, 2000)
	if not name or not EMAIL_RE.match(email):
		frappe.throw("Name and a valid email are required")

	medium = HEARD.get(_clean(heard, 20).lower())
	referrer = referred_salesperson(_clean(ref, 40))

	for doctype, value in (("UTM Source", SOURCE), ("UTM Medium", medium)):
		if value and not frappe.db.exists(doctype, value):
			frappe.get_doc({"doctype": doctype, "name": value}).insert(ignore_permissions=True)

	# One lead per email address.
	existing = frappe.db.get_value("Lead", {"email_id": email}, "name")
	if existing:
		lead = frappe.get_doc("Lead", existing)
	else:
		lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"lead_name": name,
				"email_id": email,
				"company_name": company,
				"utm_source": SOURCE,
				"utm_medium": medium,
				"qualification_status": "Unqualified",
			}
		)
	if medium and not lead.utm_medium:
		lead.utm_medium = medium
	# The planner's brief is one line per item; the note is HTML, so keep the lines.
	note = frappe.utils.escape_html(message).replace("\n", "<br>") if message else ""
	if referrer:
		who = frappe.db.get_value("User", referrer, "full_name") or referrer
		note = f"Referred by {frappe.utils.escape_html(who)} (planner link)" + (f"<br><br>{note}" if note else "")
	if note:
		lead.append("notes", {"note": note, "added_on": frappe.utils.now()})
	if existing:
		lead.save(ignore_permissions=True)
	else:
		lead.insert(ignore_permissions=True)

	# Their task is still open: add to it rather than starting a second one.
	subject = f"{SUBJECT_PREFIX}{lead.name}"
	open_task = frappe.db.get_value("Task", {"subject": subject, "status": "Open"}, "name")
	if open_task:
		frappe.get_doc("Task", open_task).add_comment(
			"Comment", "New message from the website: see the latest note on the lead."
		)
		return {"lead": lead.name}

	link = frappe.utils.get_url_to_form("Lead", lead.name)
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": "Open",
			"priority": "Medium",
			"department": "Account Management - K",
			"description": (
				f'Lead link: <a href="{link}">{lead.name}</a><br>'
				f'Contact details: see the lead. Do not add names, email or phone in this task.<br><br>'
				"Came in through the kiluth.com contact form.<br><br>"
				"<b>Done when</b> Sales has decided, and the lead in the Portal shows it: Qualified, "
				"or Unqualified with Status Do Not Contact and the reason written on the lead."
			),
		}
	).insert(ignore_permissions=True)

	assign(task.name, task.subject, [referrer or pick_salesperson()])
	return {"lead": lead.name}
