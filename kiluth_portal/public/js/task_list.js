// Task list and Task Board additions.
//
// List, phone: who has each task. The desk shows assignees in a block it hides at
// phone width (`.list-row-activity.hidden-xs`), so add the names under each row.
//
// Board, every screen: a one-tap My tasks button. A board has no quick-filter bar,
// and its Filter button sits in `.custom-actions`, which is `hidden-xs hidden-md`,
// so on a phone there was no way to filter at all. On a phone Filter moves into
// the same bar.
//
// Board, touch screens: cards and columns don't drag. A finger on a card was
// enough to change a task's status by accident (Poom, 2026-11-01). Status changes
// on the task page there.
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

	const is_touch = () => frappe.is_mobile() || window.matchMedia("(pointer: coarse)").matches;

	function setup_board(listview) {
		if (listview.kiluth_bar) return;
		const bar = (listview.kiluth_bar = $(`<div class="kiluth-board-bar" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 0;"></div>`));
		const mine = $(`<button type="button" class="btn btn-sm"></button>`).appendTo(bar);
		bar.insertBefore(listview.$result);
		if (frappe.is_mobile()) {
			listview.$filter_section.appendTo(bar);
			// Opens the quick-filter bar a board doesn't have, and throws.
			listview.$filter_section.find(".filter-toggle").hide();
		}

		const is_mine = () => listview.filter_area.get().some((f) => f[1] === "_assign");
		const sync = () => {
			const on = is_mine();
			mine.toggleClass("btn-primary", on).toggleClass("btn-default", !on);
			mine.attr("aria-pressed", on).text(on ? `${__("My tasks")} ✕` : __("My tasks"));
			if (!is_touch()) return;
			listview.$result.find(".kanban, .kanban-cards").each(function () {
				Sortable.get(this)?.option("disabled", true);
			});
		};

		mine.on("click", async () => {
			if (is_mine()) await listview.filter_area.remove("_assign");
			else await listview.filter_area.add([[listview.doctype, "_assign", "like", `%${frappe.session.user}%`]]);
			sync();
		});
		// The board redraws its columns on every refresh, which makes new drag handlers.
		new MutationObserver(sync).observe(listview.$result.get(0), { childList: true, subtree: true });
		sync();
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

	// A board never calls `onload`: KanbanView replaces setup_view, which is what does.
	const board = frappe.views.KanbanView?.prototype;
	if (board && !board.kiluth_render) {
		board.kiluth_render = board.render;
		board.render = function () {
			this.kiluth_render();
			if (this.doctype === "Task") setup_board(this);
		};
	}
})();
