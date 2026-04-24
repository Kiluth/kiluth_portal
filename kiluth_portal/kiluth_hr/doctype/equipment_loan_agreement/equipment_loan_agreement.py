import frappe
from frappe.model.document import Document


ACK_NOTIFICATION = "Equipment Loan Agreement Employee Ack"


class EquipmentLoanAgreement(Document):
	def validate(self):
		self._stamp_acknowledgment()
		self._ensure_agreement_acknowledged()

	def _stamp_acknowledgment(self):
		"""Stamp who/when on first tick. Locked once set — never overwritten."""
		if self.i_agree_to_the_terms and not self.acknowledged_by:
			self.acknowledged_by = frappe.session.user
			self.acknowledged_on = frappe.utils.now_datetime()

	def _ensure_agreement_acknowledged(self):
		if self.docstatus == 1 and not self.i_agree_to_the_terms:
			frappe.throw("Agreement must be acknowledged by the borrower before submission.")


@frappe.whitelist()
def resend_acknowledgment_email(name: str):
	"""Re-fire the employee-facing acknowledgment email for an unsigned draft ELA.

	HR triggers this from the form when the employee lost the original email.
	Reuses the existing Notification record so the content never drifts.
	"""
	doc = frappe.get_doc("Equipment Loan Agreement", name)

	if doc.docstatus != 0 or doc.i_agree_to_the_terms:
		frappe.throw("Resend is only available for draft agreements awaiting acknowledgment.")

	notification = frappe.get_doc("Notification", ACK_NOTIFICATION)
	notification.send(doc)
