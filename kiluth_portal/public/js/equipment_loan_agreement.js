// Paperless acknowledgment flow.
// Borrower sees "I Acknowledge" on their own draft ELA — clicking ticks the
// checkbox and saves, which stamps acknowledged_by/on server-side.
// HR sees "Resend Acknowledgment Email" to re-fire the ack notification if
// the employee lost the original.
frappe.ui.form.on("Equipment Loan Agreement", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		if (frm.doc.i_agree_to_the_terms) return;

		add_acknowledge_button(frm);
		add_resend_button(frm);
	},
});

function add_acknowledge_button(frm) {
	if (!frm.doc.employee) return;
	frappe.db.get_value("Employee", frm.doc.employee, "user_id").then((res) => {
		const uid = res && res.message ? res.message.user_id : null;
		if (uid !== frappe.session.user) return;

		frm.add_custom_button(__("I Acknowledge"), () => {
			frappe.confirm(
				__(
					"By acknowledging, you confirm you have read the Equipment Loan Agreement terms and accept custody of the listed assets. Your user account and a timestamp will be logged as your digital signature."
				),
				() => {
					frm.set_value("i_agree_to_the_terms", 1);
					frm.save();
				}
			);
		}).addClass("btn-primary");
	});
}

function add_resend_button(frm) {
	const is_hr =
		frappe.user.has_role("HR Manager") || frappe.user.has_role("System Manager");
	if (!is_hr) return;

	frm.add_custom_button(__("Resend Acknowledgment Email"), () => {
		frappe.call({
			method:
				"kiluth_portal.kiluth_hr.doctype.equipment_loan_agreement.equipment_loan_agreement.resend_acknowledgment_email",
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Sending..."),
			callback: () =>
				frappe.show_alert({
					message: __("Acknowledgment email sent"),
					indicator: "green",
				}),
		});
	});
}
