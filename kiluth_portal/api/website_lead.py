"""Website enquiries from the kiluth.com contact form.

Called only by the kiluth.com form Lambda (kiluth-infra), signed in as the
website bot user. That user has no roles and no doctype permissions: this one
method is all its API key can do.

Follows Lead Intake (docs.kiluth.com/marketing/lead-intake):
  1. the Lead holds the person's details (UTM Source "Website", Unqualified);
  2. one task "Qualify lead: <id>" holds only the link, assigned to Sales.
The assignment email is how Sales hears about it.

  POST /api/method/kiluth_portal.api.website_lead.create_website_lead
       name, email, company (optional), message (optional)
  response = {"lead": "CRM-LEAD-2026-00042"}
"""

from __future__ import annotations

import re

import frappe
from frappe.desk.form import assign_to

BOT_USER = "website-bot@kiluth.com"
SALES_ASSIGNEE = "phuttipan.samranruen@kiluth.com"  # Reaw (Poom, 2026-10-22)
SOURCE = "Website"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean(value, limit: int) -> str:
	return (value or "").strip()[:limit]


@frappe.whitelist(methods=["POST"])
def create_website_lead(name=None, email=None, company=None, message=None):
	if frappe.session.user != BOT_USER:
		frappe.throw("Not allowed", frappe.PermissionError)

	name = _clean(name, 140)
	email = _clean(email, 254).lower()
	company = _clean(company, 140)
	message = _clean(message, 2000)
	if not name or not EMAIL_RE.match(email):
		frappe.throw("Name and a valid email are required")

	if not frappe.db.exists("UTM Source", SOURCE):
		frappe.get_doc({"doctype": "UTM Source", "name": SOURCE}).insert(ignore_permissions=True)

	# One lead per email address: a repeat enquiry adds a note and a new task.
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
				"qualification_status": "Unqualified",
			}
		)
	if message:
		lead.append("notes", {"note": frappe.utils.escape_html(message), "added_on": frappe.utils.now()})
	if existing:
		lead.save(ignore_permissions=True)
	else:
		lead.insert(ignore_permissions=True)

	link = frappe.utils.get_url_to_form("Lead", lead.name)
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": f"Qualify lead: {lead.name}",
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

	# Frappe 16: the public add() always checks permissions, and the bot has none.
	assign_to._add(
		{"assign_to": [SALES_ASSIGNEE], "doctype": "Task", "name": task.name, "description": task.subject},
		ignore_permissions=True,
	)
	return {"lead": lead.name}
