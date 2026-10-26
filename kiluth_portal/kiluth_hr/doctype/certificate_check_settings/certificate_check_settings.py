import frappe
from frappe import _
from frappe.model.document import Document


class CertificateCheckSettings(Document):
	def validate(self):
		if not (self.model_id or "").strip().startswith(("global.anthropic.", "anthropic.")):
			frappe.throw(_("Model ID must be a Claude model on Bedrock, such as global.anthropic.claude-sonnet-4-6."))
		if (self.max_tokens or 0) < 1000:
			frappe.throw(_("Max output tokens must be at least 1000."))
