"""Save Certificate Check Settings once, so its defaults are real values.

A Single that was never saved reads its Check fields as 0, which would turn
the check off. Starts in dry run: the job comments what it would do while the
workspace's certify-review skill still signs, until Poom turns dry run off.
"""

import frappe


def execute():
	s = frappe.get_single("Certificate Check Settings")
	s.enabled = 1
	s.dry_run = 1
	s.model_id = s.model_id or "global.anthropic.claude-sonnet-4-6"
	s.max_tokens = s.max_tokens or 8000
	s.save(ignore_permissions=True)
