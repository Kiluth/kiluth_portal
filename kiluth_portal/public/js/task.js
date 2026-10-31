// The task's id, always on show with a copy button. The desk has a hidden copy tap
// on the small id under the title (form/toolbar.js), which a phone doesn't show.
function show_task_id(frm) {
	frm.page.main.find(".kiluth-task-id").remove();
	if (frm.is_new()) return;
	const bar = $(`<div class="kiluth-task-id" style="display: flex; align-items: center; gap: 8px; padding: 8px 15px; font-size: 13px;">
		<span class="text-muted" style="font-family: var(--font-stack-monospace, monospace); user-select: all;"></span>
		<button type="button" class="btn btn-default btn-xs">${__("Copy")}</button>
	</div>`);
	bar.find("span").text(frm.docname);
	bar.find("button")
		.attr("aria-label", __("Copy {0}", [frm.docname]))
		.on("click", () => frappe.utils.copy_to_clipboard(frm.docname));
	frm.page.main.prepend(bar);
}

// Who has this task, on a phone. The desk keeps Assigned To in the form sidebar,
// which a phone doesn't show, so it goes in the dashboard headline there.
frappe.ui.form.on("Task", {
	refresh(frm) {
		show_task_id(frm);
		if (!frappe.is_mobile() || frm.is_new()) return;
		const names = (frm.get_docinfo().assignments || []).map((a) => frappe.user.full_name(a.owner));
		const who = names.length ? names.join(", ") : __("Nobody");
		frm.dashboard.set_headline(`${__("Assigned to")}: ${frappe.utils.escape_html(who)}`);
	},
});
