// Who has this task, on a phone. The desk keeps Assigned To in the form sidebar,
// which a phone doesn't show, so it goes in the dashboard headline there.
frappe.ui.form.on("Task", {
	refresh(frm) {
		if (!frappe.is_mobile() || frm.is_new()) return;
		const names = (frm.get_docinfo().assignments || []).map((a) => frappe.user.full_name(a.owner));
		const who = names.length ? names.join(", ") : __("Nobody");
		frm.dashboard.set_headline(`${__("Assigned to")}: ${frappe.utils.escape_html(who)}`);
	},
});
