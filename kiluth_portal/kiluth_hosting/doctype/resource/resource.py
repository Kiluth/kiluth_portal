import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate

MA_MARGIN = 0.25


def compute_resource_status(created_date, expiry_date, today_str):
	if not created_date or not expiry_date:
		return "Draft"
	if str(created_date) > today_str:
		return "Planned"
	if str(expiry_date) <= today_str:
		return "Expired"
	return "Active"


class Resource(Document):
	def before_save(self):
		self._auto_calc_ma_cost()
		self._auto_set_status()

	def _auto_calc_ma_cost(self):
		if self.resource_type != "MA":
			return
		if not self.project or not self.ma_period_months:
			return

		estimated = frappe.db.get_value("Project", self.project, "estimated_costing")
		if not estimated:
			return

		self.cost = str(flt(estimated) * MA_MARGIN / 12 * flt(self.ma_period_months))

	def _auto_set_status(self):
		if self.status in ("Archived", "Deleted"):
			return
		self.status = compute_resource_status(self.created_date, self.expiry_date, nowdate())
