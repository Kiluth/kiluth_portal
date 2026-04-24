import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

MA_MARGIN = 0.25


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
		if self.status not in ("Active", "Expired"):
			return
		if not self.expiry_date:
			return

		self.status = "Expired" if getdate(self.expiry_date) < getdate(nowdate()) else "Active"
