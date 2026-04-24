frappe.ui.form.on("Resource", {
	refresh(frm) {
		apply_project_filter(frm);
	},

	customer(frm) {
		frm.set_value("project", null);
		apply_project_filter(frm);
	},

	resource_type(frm) {
		recalc_ma_cost(frm);
	},

	project(frm) {
		recalc_ma_cost(frm);
	},

	ma_period_months(frm) {
		recalc_ma_cost(frm);
	},
});

function apply_project_filter(frm) {
	frm.set_query("project", () => ({
		filters: frm.doc.customer ? { customer: frm.doc.customer } : {},
	}));
}

async function recalc_ma_cost(frm) {
	if (frm.doc.resource_type !== "MA") return;
	if (!frm.doc.project || !frm.doc.ma_period_months) return;

	const { message: estimated } = await frappe.db.get_value(
		"Project",
		frm.doc.project,
		"estimated_costing",
	);

	if (!estimated?.estimated_costing) return;

	const cost = (0.25 * estimated.estimated_costing / 12) * frm.doc.ma_period_months;
	frm.set_value("cost", cost);
}
