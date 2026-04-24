frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		apply_project_filter(frm);
	},

	customer(frm) {
		frm.set_value("project", null);
		apply_project_filter(frm);
	},
});

function apply_project_filter(frm) {
	frm.set_query("project", () => ({
		filters: frm.doc.customer ? { customer: frm.doc.customer } : {},
	}));
}
