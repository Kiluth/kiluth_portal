"""Send HRMS's two leave emails in the Kiluth design (2026-10-27).

HRMS renders the Email Templates named in HR Settings (Leave Approval
Notification, Leave Status Notification). Their bodies are DB records HRMS
creates once at install, so a file can't shadow them. This turns on "Use HTML"
and points the HTML at our files with an include, so later edits are git-only:
  templates/emails/hrms_leave_approval.html
  templates/emails/hrms_leave_status.html
HRMS's original body stays untouched in the `response` field. To undo, untick
"Use HTML" on the Email Template (and retype the old subject if wanted).
HRMS upgrades don't touch existing Email Templates, so this survives them.
"""

import frappe

TEMPLATES = {
	# HR Settings field: (subject, our file)
	"leave_approval_notification_template": (
		"Leave request from {{ employee_name or employee }}: {{ name }}",
		"hrms_leave_approval",
	),
	"leave_status_notification_template": (
		"Leave {{ ('cancelled' if docstatus == 2 else status|lower) }}: {{ name }}",
		"hrms_leave_status",
	),
}


def execute():
	for field, (subject, file) in TEMPLATES.items():
		name = frappe.db.get_single_value("HR Settings", field)
		if not name or not frappe.db.exists("Email Template", name):
			continue
		frappe.db.set_value(
			"Email Template",
			name,
			{
				"subject": subject,
				"use_html": 1,
				"response_html": '{% include "kiluth_portal/templates/emails/' + file + '.html" %}',
			},
		)
