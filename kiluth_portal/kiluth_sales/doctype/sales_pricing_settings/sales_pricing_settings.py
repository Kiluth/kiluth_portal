import frappe
from frappe import _
from frappe.model.document import Document


class SalesPricingSettings(Document):
	def validate(self):
		if (self.kiluth_markup_min or 0) > (self.kiluth_markup_max or 0):
			frappe.throw(_("Kiluth markup minimum can't be above the maximum."))
		if not (self.kiluth_markup_min or 0) <= (self.kiluth_markup_default or 0) <= (self.kiluth_markup_max or 0):
			frappe.throw(_("Kiluth markup default must sit inside the allowed band."))
		if not (self.honesty_strong_under_pct or 0) <= (self.honesty_possible_under_pct or 0) <= (self.honesty_pushback_pct or 0):
			frappe.throw(_("Honesty-check bands must go up: strong under, then possible under, then pushback."))
