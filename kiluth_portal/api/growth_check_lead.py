"""Growth Check results from kiluth.com → a Lead in the Kiluth Portal.

Called only by the growth-check Lambda (kiluth-infra), signed in as the website
bot user, after the visitor asks for their result by email. Rules from
Marketing's readiness-quiz-2026-10.md §6–§7 and Legal's check:

  - the Lead gets UTM Source "Website", UTM Medium "Growth Check", Unqualified;
  - a note holds the result (type, four area scores, Q11–Q12) and the
    marketing choice with its time and the exact wording shown, so the consent
    can be proven later;
  - a "Qualify lead" task only when Q12 says they want help (wants_help=1).
    The score never decides it;
  - one Lead per email: a repeat adds a note, and comments on the open task
    instead of making a second one. A returning visitor who wants help and has
    no open task gets a new one.

  POST /api/method/kiluth_portal.api.growth_check_lead.create_growth_check_lead
       email, name, company, result, wants_help, marketing, marketing_text, marketing_at
  response = {"lead": "CRM-LEAD-2026-00042", "task": "TASK-…" | null}
"""

from __future__ import annotations

import frappe

from kiluth_portal.api.website_lead import BOT_USER, EMAIL_RE, SOURCE, _clean
from kiluth_portal.utils.lead_routing import LEADS_PROJECT, SUBJECT_PREFIX, assign, pick_salesperson

MEDIUM = "Growth Check"


def _truthy(value) -> bool:
	return str(value or "").strip().lower() in ("1", "true", "yes")


def consent_note(marketing: bool, text: str, at: str) -> str:
	esc = frappe.utils.escape_html
	choice = "Yes" if marketing else "No"
	return (
		f"<b>Marketing emails:</b> {choice} ({esc(at)}, Growth Check)<br>"
		f"Wording shown: “{esc(text)}”"
	)


@frappe.whitelist(methods=["POST"])
def create_growth_check_lead(
	email=None, name=None, company=None, result=None, wants_help=None,
	marketing=None, marketing_text=None, marketing_at=None,
):
	if frappe.session.user != BOT_USER:
		frappe.throw("Not allowed", frappe.PermissionError)

	email = _clean(email, 254).lower()
	if not EMAIL_RE.match(email):
		frappe.throw("A valid email is required")
	name = _clean(name, 140) or email.split("@")[0]
	company = _clean(company, 140)
	result = _clean(result, 4000)
	marketing_text = _clean(marketing_text, 500)
	marketing_at = _clean(marketing_at, 40) or frappe.utils.now()
	if not marketing_text:
		frappe.throw("The consent wording is required")
	wants_help = _truthy(wants_help)
	marketing = _truthy(marketing)

	for doctype, value in (("UTM Source", SOURCE), ("UTM Medium", MEDIUM)):
		if not frappe.db.exists(doctype, value):
			frappe.get_doc({"doctype": doctype, "name": value}).insert(ignore_permissions=True)

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
				"utm_medium": MEDIUM,
				"qualification_status": "Unqualified",
			}
		)
	note = "<b>Growth Check result</b><br>" + frappe.utils.escape_html(result).replace("\n", "<br>")
	note += "<br><br>" + consent_note(marketing, marketing_text, marketing_at)
	lead.append("notes", {"note": note, "added_on": frappe.utils.now()})
	if existing:
		lead.save(ignore_permissions=True)
	else:
		lead.insert(ignore_permissions=True)

	subject = f"{SUBJECT_PREFIX}{lead.name}"
	open_task = frappe.db.get_value("Task", {"subject": subject, "status": "Open"}, "name")
	if open_task:
		frappe.get_doc("Task", open_task).add_comment(
			"Comment", "New Growth Check result: see the latest note on the lead."
		)
		return {"lead": lead.name, "task": None}
	if not wants_help:
		return {"lead": lead.name, "task": None}

	link = frappe.utils.get_url_to_form("Lead", lead.name)
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": LEADS_PROJECT,
			"status": "Open",
			"priority": "Medium",
			"department": "Account Management - K",
			"description": (
				f'Lead link: <a href="{link}">{lead.name}</a><br>'
				f'Contact details: see the lead. Do not add names, email or phone in this task.<br><br>'
				"Came in through the Growth Check on kiluth.com: they said they're looking for help. "
				"Their result is in the lead's notes.<br><br>"
				"<b>Done when</b> Sales has decided, and the lead in the Portal shows it: Qualified, "
				"or Unqualified with Status Do Not Contact and the reason written on the lead."
			),
		}
	).insert(ignore_permissions=True)
	assign(task.name, task.subject, [pick_salesperson()])
	return {"lead": lead.name, "task": task.name}
