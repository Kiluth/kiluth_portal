# Copyright (c) 2026, Kiluth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document as FrappeDocument
from frappe.model.naming import make_autoname

# Per-type naming series. The Document Type drives the ID prefix; ERPNext
# auto-increments each series independently (AGR-00001, CR-00001, ...).
NAMING_SERIES = {
	"Agreement / Contract": "AGR-.#####",
	"Change Request / Change Order": "CR-.#####",
	"NDA": "NDA-.#####",
	"Maintenance Agreement": "MA-.#####",
	"Sign-off / Acceptance": "SGN-.#####",
}


class Document(FrappeDocument):
	def autoname(self):
		series = NAMING_SERIES.get(self.document_type)
		if not series:
			frappe.throw("Select a valid Document Type before saving.")
		self.name = make_autoname(series)

	def validate(self):
		self._require_signed_pdf()
		self._lock_after_signed()

	def _require_signed_pdf(self):
		"""A document can't be marked Signed without the finalized PDF attached."""
		if self.status == "Signed" and not self.signed_pdf:
			frappe.throw("Attach the signed PDF before setting the status to Signed.")

	def _lock_after_signed(self):
		"""Once Signed, only a System Manager may edit the record (protects the executed document)."""
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if before and before.status == "Signed" and "System Manager" not in frappe.get_roles():
			frappe.throw(
				"This document is Signed and locked. Only an administrator can change it."
			)
