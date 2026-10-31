// Who has each task, on a phone. The desk shows assignees in a block it hides at
// phone width (`.list-row-activity.hidden-xs`), so add the names under each row.
// The Task Board has its own file: task_board.js.
(() => {
	const settings = frappe.listview_settings["Task"];
	const onload = settings.onload;

	function show_assignees(listview) {
		for (const doc of listview.data) {
			const row = listview.$result.find(`.list-row-checkbox[data-name="${CSS.escape(doc.name)}"]`).closest(".list-row-container");
			if (!row.length || row.find(".kiluth-assignee").length) continue;
			const names = JSON.parse(doc._assign || "[]").map((u) => frappe.user.full_name(u));
			const who = names.length ? names.join(", ") : __("Nobody");
			row.find(".list-row").css("border-bottom", "none");
			row.append(`<div class="kiluth-assignee text-muted small"
				style="padding: 0 15px 8px; margin-top: -6px; border-bottom: 1px solid var(--border-color);">${frappe.utils.escape_html(who)}</div>`);
		}
	}

	settings.onload = function (listview) {
		onload?.(listview);
		if (listview.view_name === "List" && frappe.is_mobile()) {
			const render_list = listview.render_list;
			listview.render_list = function () {
				render_list.call(this);
				show_assignees(this);
			};
		}
	};
})();
