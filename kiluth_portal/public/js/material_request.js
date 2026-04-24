// Narrow the item picker to the Kiluth Catalog tree only. Existing Items used
// for client invoicing / recurring expense entries stay untouched system-wide —
// they just don't appear in the MR dropdown.
//
// Also nudges the requester to put model/brand/specs in the description so
// procurement can act on the ticket without a back-and-forth.
const KILUTH_CATALOG_GROUPS = [
	"Laptop",
	"Monitor",
	"Peripheral",
	"Audio",
	"Networking",
	"Furniture",
	"Software",
	"Other",
];

frappe.ui.form.on("Material Request", {
	setup(frm) {
		frm.set_query("item_code", "items", () => ({
			filters: { item_group: ["in", KILUTH_CATALOG_GROUPS] },
		}));
	},
});

frappe.ui.form.on("Material Request Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		if (row.description && row.description.trim()) return;

		frappe.show_alert({
			message: __(
				"Tip: describe the specific item (model, brand, specs) in the Description so procurement can order the exact right thing."
			),
			indicator: "blue",
		});
	},
});
