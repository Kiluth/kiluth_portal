// The Task Board, redrawn for reading a task at a glance on a phone (Poom, 2026-11-01).
//
// A card says what to do, how urgent it is, whose project it is and who has it.
// The board's own card fields aren't used, so the card doesn't depend on Customize
// Cards. The + on the desk's card is gone: it adds a second assignee, and a task
// has one. Hand a task over on the task page.
//
// My tasks: a board has no quick-filter bar, and its Filter button sits in
// `.custom-actions`, which is `hidden-xs hidden-md`, so a phone couldn't filter.
//
// Touch screens: cards and columns don't drag, because a finger on a card was enough
// to change a task's status by accident. Status changes on the task page there.
(() => {
	const proto = frappe.views.KanbanView?.prototype;
	if (!proto || proto.kiluth_render) return;

	const FIELDS = ["priority", "exp_end_date", "hygiene"];
	const is_touch = () => frappe.is_mobile() || window.matchMedia("(pointer: coarse)").matches;
	const esc = frappe.utils.escape_html;
	const project_names = {};

	function add_styles() {
		if (document.getElementById("kiluth-board-css")) return;
		$(`<style id="kiluth-board-css">
			:root {
				--kb-edge: var(--gray-300);
				--kb-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
				--kb-high: var(--red-600);
				--kb-high-bg: var(--red-50);
				--kb-medium: var(--orange-700);
				--kb-medium-bg: var(--orange-50);
				--kb-low: var(--text-muted);
			}
			[data-theme="dark"] {
				--kb-edge: var(--gray-700);
				--kb-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
				--kb-high: #ff9d97;
				--kb-high-bg: rgba(229, 72, 77, 0.2);
				--kb-medium: #ffc27a;
				--kb-medium-bg: rgba(245, 158, 11, 0.16);
			}
			.kiluth-board-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 0; }
			.kiluth-board-bar .kb-total { margin-left: auto; font-size: 12px; color: var(--text-muted); }
			/* custom-btn-group is Select Kanban: on a phone its label is hidden-xs, which
			   left an empty button, and there is only one board. */
			.kiluth-board-bar .filter-x-button, .kiluth-board-bar .filter-toggle,
			.kiluth-board-bar .custom-btn-group { display: none; }
			.kiluth-board-bar .btn-group .filter-button { border-radius: var(--border-radius-md, 8px) !important; }
			.kanban .kanban-column-title .kb-count { margin-left: 6px; font-size: 12px; font-weight: 400; color: var(--text-muted); }
			.kanban .kanban-column .kanban-cards .kanban-card-wrapper .kanban-card.content {
				position: relative; min-height: 0; margin-top: 10px; overflow: hidden;
				background: var(--kanban-card-bg); border: 1px solid var(--kb-edge); border-radius: 10px;
				box-shadow: var(--kb-shadow);
			}
			.kanban .kb-card { display: flex; flex-direction: column; gap: 8px; padding: 12px; }
			.kanban .kb-card[data-priority="High"], .kanban .kb-card[data-priority="Urgent"] { box-shadow: inset 3px 0 0 var(--kb-high); }
			.kanban .kb-card[data-priority="Medium"] { box-shadow: inset 3px 0 0 var(--kb-medium); }
			.kb-top { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 12px; color: var(--text-muted); }
			.kb-priority { flex: none; padding: 1px 8px; border-radius: 999px; font-weight: 600; color: var(--kb-low); background: var(--subtle-fg, var(--control-bg)); }
			[data-priority="High"] .kb-priority, [data-priority="Urgent"] .kb-priority { color: var(--kb-high); background: var(--kb-high-bg); }
			[data-priority="Medium"] .kb-priority { color: var(--kb-medium); background: var(--kb-medium-bg); }
			.kb-project { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.kb-due { flex: none; }
			.kb-due.late { color: var(--kb-high); font-weight: 600; }
			.kb-title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden;
				font-size: 15px; line-height: 1.35; font-weight: 500; color: var(--text-color); text-decoration: none; }
			.kb-title::after { content: ""; position: absolute; inset: 0; }
			.kb-title:hover { color: var(--text-color); text-decoration: none; }
			.kb-foot { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; color: var(--text-color); }
			.kb-person { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 0; }
			.kb-person .kb-name { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.kb-person.nobody { color: var(--kb-high); font-weight: 600; }
			.kb-note { flex: none; font-size: 12px; color: var(--text-muted); display: inline-flex; align-items: center; gap: 3px; }
			.kb-note.bad { color: var(--kb-high); font-weight: 600; }
			.kb-touch .kanban .add-card, .kb-touch .kanban .column-options { display: none; }
			.kb-touch .kanban { scroll-snap-type: x proximity; }
			.kb-touch .kanban .kanban-column .kanban-cards { max-height: calc(100dvh - 170px); }
			.kb-touch .kanban .kanban-column { scroll-snap-align: center; }
		</style>`).appendTo("head");
	}

	function due_html(date, status) {
		if (!date) return "";
		const late = date < frappe.datetime.get_today() && !["Completed", "Cancelled"].includes(status);
		const text = frappe.datetime.str_to_user(date);
		return `<span class="kb-due ${late ? "late" : ""}">${late ? __("Late") + " · " : ""}${esc(text)}</span>`;
	}

	function person_html(doc) {
		const people = JSON.parse(doc._assign || "[]");
		if (!people.length) return `<span class="kb-person nobody">${__("Nobody")}</span>`;
		const name = frappe.user_info(people[0]).fullname || people[0];
		const more = people.length > 1 ? ` +${people.length - 1}` : "";
		return `<span class="kb-person">${frappe.avatar(people[0], "avatar-small")}<span class="kb-name">${esc(name)}${more}</span></span>`;
	}

	function card_html(doc, status) {
		const priority = doc.priority || "Low";
		const comments = doc._comment_count > 0
			? `<span class="kb-note">${frappe.utils.icon("es-line-chat-alt", "sm")}${doc._comment_count}</span>` : "";
		const failing = doc.hygiene === "Fail" ? `<span class="kb-note bad">${__("Needs fixing")}</span>` : "";
		return `<div class="kb-card" data-priority="${esc(priority)}">
			<div class="kb-top">
				<span class="kb-priority">${esc(__(priority))}</span>
				<span class="kb-project" data-project="${esc(doc.project || "")}">${esc(project_names[doc.project] || doc.project || __("No project"))}</span>
				${due_html(doc.exp_end_date, status)}
			</div>
			<a class="kb-title" href="${frappe.utils.get_form_link("Task", doc.name)}">${esc(doc.subject || doc.name)}</a>
			<div class="kb-foot">${person_html(doc)}${failing}${comments}<span class="kb-note" title="${esc(doc.name)}">#${esc(doc.name.split("-").pop())}</span></div>
		</div>`;
	}

	function draw_cards(listview) {
		const docs = Object.fromEntries(listview.data.map((d) => [d.name, d]));
		for (const wrapper of listview.$result.find(".kanban-card-wrapper:not([data-kb])")) {
			const doc = docs[decodeURIComponent(wrapper.dataset.name)];
			if (!doc) continue;
			const status = $(wrapper).closest(".kanban-column").attr("data-column-value");
			wrapper.dataset.kb = "1";
			$(wrapper).find(".kanban-card-body").replaceWith(card_html(doc, status));
		}
		for (const column of listview.$result.find(".kanban-column")) {
			const title = $(column).find(".kanban-column-title .kanban-title");
			const count = $(column).find(".kanban-card-wrapper").length;
			const label = title.find(".kb-count");
			if (label.text() === String(count)) continue;
			if (label.length) label.text(count);
			else title.append(`<span class="kb-count">${count}</span>`);
		}
	}

	function setup_bar(listview) {
		const bar = (listview.kiluth_bar = $(`<div class="kiluth-board-bar"></div>`));
		const mine = $(`<button type="button" class="btn btn-sm kb-mine"></button>`).appendTo(bar);
		const total = $(`<span class="kb-total"></span>`);
		bar.insertBefore(listview.$result);
		if (frappe.is_mobile()) listview.$filter_section.appendTo(bar);
		bar.append(total);

		const is_mine = () => listview.filter_area.get().some((f) => f[1] === "_assign");
		const sync = () => {
			const on = is_mine();
			mine.toggleClass("btn-primary", on).toggleClass("btn-default", !on);
			mine.attr("aria-pressed", on).text(on ? `${__("My tasks")} ✕` : __("My tasks"));
			total.text(__("{0} tasks", [listview.data.length]));
			draw_cards(listview);
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
		// The board redraws its columns on every refresh, which brings back the desk's
		// cards and new drag handlers.
		new MutationObserver(sync).observe(listview.$result.get(0), { childList: true, subtree: true });
		sync();
	}

	function setup_board(listview) {
		if (listview.kiluth_bar) return;
		add_styles();
		$(document.documentElement).toggleClass("kb-touch", is_touch());
		listview.page.set_title(__("Task Board"));
		setup_bar(listview);
		frappe.db.get_list("Project", { fields: ["name", "project_name"], limit: 0 }).then((rows) => {
			for (const row of rows) project_names[row.name] = row.project_name;
			listview.$result.find(".kb-project[data-project]").each(function () {
				this.textContent = project_names[this.dataset.project] || this.textContent;
			});
		});
	}

	// A board never calls the list settings' `onload`: KanbanView replaces setup_view,
	// which is what does. So these wrap the class, for Task only.
	proto.kiluth_render = proto.render;
	proto.render = function () {
		this.kiluth_render();
		if (this.doctype === "Task") setup_board(this);
	};

	// Always fetched, whatever the board's card fields say.
	const set_fields = proto.set_fields;
	proto.set_fields = function () {
		set_fields.call(this);
		if (this.doctype === "Task") FIELDS.forEach((f) => this._add_field(f, this.doctype));
	};

	// The "Not Saved" dot means a filter differs from the one saved on the shared
	// board, which a person filtering their own view shouldn't have to care about.
	const on_filter_change = proto.on_filter_change;
	proto.on_filter_change = function () {
		on_filter_change.call(this);
		if (this.doctype === "Task") this.page.clear_indicator();
	};
})();
