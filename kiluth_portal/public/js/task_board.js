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
// to change a task's status by accident. The status button on each card moves it
// instead (task_sheet.js), and the tabs jump between columns.
//
// Touch screens scroll once: the page goes up and down and the board only sideways.
// The desk gave each column its own scroll inside the page's (see one_scroll).
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
			.kb-move { position: relative; z-index: 1; flex: none; display: none; align-items: center; gap: 4px; min-height: 32px; padding: 0 10px;
				border: 1px solid var(--kb-edge); border-radius: 8px; background: transparent; color: var(--text-color); font-size: 13px; }
			.kb-touch .kb-move { display: inline-flex; }
			.kb-move::after { content: "▾"; font-size: 10px; color: var(--text-muted); }
			.kb-id { flex: none; font-size: 12px; color: var(--text-muted); }
			.kb-tabs { display: none; position: sticky; z-index: 5; align-items: center; gap: 6px; overflow-x: auto; scrollbar-width: none;
				margin: 0 -2px; padding: 2px 2px 6px; background: var(--bg-color); }
			.kb-tabs::-webkit-scrollbar { display: none; }
			.kb-touch .kb-tabs { display: flex; }
			.kb-tabs button { flex: none; display: inline-flex; gap: 5px; align-items: center; height: 34px; padding: 0 12px; border: 1px solid transparent;
				border-radius: 999px; background: transparent; color: var(--text-muted); font-size: 13px; white-space: nowrap; }
			.kb-tabs button[aria-current="true"] { color: var(--text-color); font-weight: 600; border-color: var(--kb-edge); background: var(--control-bg); }
			.kanban .kanban-cards:not(:has(.kanban-card-wrapper))::after { content: attr(data-empty); display: block; padding: 24px 12px; text-align: center;
				font-size: 13px; color: var(--text-muted); }
			.kb-touch .kanban .add-card, .kb-touch .kanban .kanban-column-header { display: none; }
			.kb-touch .kanban { margin: 0; gap: 12px; }
			.kb-touch .kanban .kanban-column { flex: 0 0 100%; min-width: 0; max-width: 100%; padding: 0; box-sizing: border-box; background: transparent !important; }
			.kb-touch .kanban .kanban-column .kanban-cards { margin: 0; padding: 0 1px; width: 100%; box-sizing: border-box; }
			.kb-touch .kanban { align-items: flex-start; scroll-snap-type: x proximity; overscroll-behavior-x: contain; }
			/* Keeps the page scrollable on a short list: with nothing to scroll, iOS stops the board swiping too. */
			.kb-touch .kanban { min-height: 100dvh; }
			.kb-touch .kanban .kanban-column { min-height: 0; scroll-snap-align: start; transition: none; }
			.kb-touch .kanban .kanban-column .kanban-cards { height: auto; max-height: none; overflow: visible; }
			/* Frappe lifts a hovered card to 1001, and a finger leaves a card hovered: it slid over the head. */
			.kb-touch .kanban .kanban-card-wrapper:hover { z-index: auto; }
			/* In a browser tab 100vh is taller than the screen, so past the end of the list the whole page, head included, moved up. */
			.kb-touch body[data-route^="List/Task/Kanban"] .main-section { height: 100dvh; overscroll-behavior-y: contain; }
			/* The page is as long as the column on screen: the others stop counting, without measuring anything. */
			.kb-touch .kanban:has(.kb-here):not(.kb-swiping) .kanban-column:not(.kb-here) { margin-bottom: -100000px; }
		</style>`).appendTo("head");
	}

	function due_html(date, status) {
		if (!date) return "";
		const day = String(date).slice(0, 10); // Task's dates carry a time
		const late = day < frappe.datetime.get_today() && !["Completed", "Cancelled"].includes(status);
		const text = moment(day).format("D MMM");
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
				<span class="kb-id" title="${esc(doc.name)}">#${esc(doc.name.split("-").pop())}</span>
			</div>
			<a class="kb-title" href="${frappe.utils.get_form_link("Task", doc.name)}">${esc(doc.subject || doc.name)}</a>
			<div class="kb-foot">
				${person_html(doc)}${due_html(doc.exp_end_date, status)}${failing}${comments}
				<button type="button" class="kb-move" aria-label="${esc(__("Move task, now {0}", [__(status)]))}">${esc(__(status))}</button>
			</div>
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
			$(wrapper).find(".kb-move").on("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				const task = { name: doc.name, subject: doc.subject, status, owner: doc.owner };
				kiluth.tasks.pick_status(task, (to) => kiluth.tasks.move(task, to, () => listview.refresh()));
			});
		}
		for (const column of listview.$result.find(".kanban-column")) {
			const title = $(column).find(".kanban-column-title .kanban-title");
			const count = $(column).find(".kanban-card-wrapper").length;
			const label = title.find(".kb-count");
			if (label.text() === String(count)) continue;
			if (label.length) label.text(count);
			else title.append(`<span class="kb-count">${count}</span>`);
		}
		listview.$result.find(".kanban-cards").attr("data-empty", __("Nothing here"));
	}

	const column_on_screen = (columns) => {
		const middle = window.innerWidth / 2;
		return columns.findIndex((c) => {
			const r = c.getBoundingClientRect();
			return r.left <= middle && r.right >= middle;
		});
	};

	// Phone: one tab per column, to jump there and show where you are.
	function sync_tabs(listview, tabs) {
		const columns = listview.$result.find(".kanban-column").toArray();
		const signature = columns.map((c) => `${c.dataset.columnValue}:${$(c).find(".kanban-card-wrapper").length}`).join();
		if (tabs.data("signature") !== signature) {
			tabs.data("signature", signature).empty();
			for (const column of columns) {
				const count = $(column).find(".kanban-card-wrapper").length;
				$(`<button type="button"><span>${esc(__(column.dataset.columnValue))}</span><span>${count}</span></button>`)
					.appendTo(tabs)
					.on("click", () => {
						// Looked up each time: a refresh replaces the columns.
						const now = listview.$result.find(".kanban-column").get(columns.indexOf(column));
						const board = now?.parentElement;
						if (board) board.scrollLeft += now.getBoundingClientRect().left - board.getBoundingClientRect().left;
					});
			}
		}
		const at = Math.max(column_on_screen(columns), 0);
		tabs.children().each(function (i) {
			this.setAttribute("aria-current", i === at);
		});
		// There are more tabs than fit, and the lit one has to stay in sight.
		if (tabs.data("at") === at) return;
		tabs.data("at", at);
		const tab = tabs.children().get(at);
		tabs.scrollLeft(tab.offsetLeft - (tabs.width() - tab.offsetWidth) / 2);
	}

	// The page is the only thing that scrolls up and down, so a long column and an
	// empty one share it. Each column keeps its own place: during a swipe the others
	// are shifted to where they'd be, and when the board stops the page moves to that
	// place and the shift goes, so nothing on screen jumps.
	function one_scroll(listview, tabs) {
		const page = document.querySelector(".main-section");
		const board = () => listview.$result.find(".kanban").get(0);
		const columns = () => listview.$result.find(".kanban-column").toArray();
		const tops = {};
		let timer = null;

		// A column not opened yet starts with its first card under the tabs.
		const place_of = (column) => {
			const tabs_end = parseFloat(tabs.css("top")) + tabs.outerHeight();
			const start = page.scrollTop + board().getBoundingClientRect().top - tabs_end;
			return tops[column.dataset.columnValue] ?? Math.min(page.scrollTop, start);
		};
		const mark = () => {
			if (!is_touch() || !board() || board().classList.contains("kb-swiping") || !listview.$result.is(":visible")) return;
			const all = columns();
			const now = all[column_on_screen(all)] || all[0];
			all.forEach((c) => c.classList.toggle("kb-here", c === now));
			tabs.css("top", listview.page.wrapper.find(".page-head").outerHeight());
		};
		const settle = () => {
			const old = columns().find((c) => c.classList.contains("kb-here"));
			if (old) tops[old.dataset.columnValue] = page.scrollTop;
			const shifted = columns().map((c) => [c, place_of(c)]);
			board().classList.remove("kb-swiping");
			columns().forEach((c) => (c.style.transform = ""));
			mark();
			const now = shifted.find(([c]) => c.classList.contains("kb-here"));
			if (now && now[0] !== old) page.scrollTop = now[1];
		};
		const swiped = () => {
			if (!board().classList.contains("kb-swiping")) {
				for (const column of columns()) {
					if (column.classList.contains("kb-here")) continue;
					column.style.transform = `translateY(${page.scrollTop - place_of(column)}px)`;
				}
				board().classList.add("kb-swiping");
			}
			clearTimeout(timer);
			timer = setTimeout(settle, 150);
		};
		window.addEventListener("resize", mark);
		return { mark, swiped, is_board: (el) => el === board() };
	}

	function setup_bar(listview) {
		const bar = (listview.kiluth_bar = $(`<div class="kiluth-board-bar"></div>`));
		const mine = $(`<button type="button" class="btn btn-sm kb-mine"></button>`).appendTo(bar);
		const total = $(`<span class="kb-total"></span>`);
		$(`<button type="button" class="btn btn-sm btn-default kb-list">${__("List")}</button>`)
			.appendTo(bar)
			.on("click", () => frappe.set_route("List", "Task", "List"));
		bar.insertBefore(listview.$result);
		if (frappe.is_mobile()) listview.$filter_section.appendTo(bar);
		bar.append(total);
		// Beside the bar, not in it: stuck to the top, they'd leave with the bar.
		const tabs = $(`<div class="kb-tabs"></div>`).insertAfter(bar);
		const scroll = one_scroll(listview, tabs);

		const is_mine = () => listview.filter_area.get().some((f) => f[1] === "_assign");
		const sync = () => {
			const on = is_mine();
			mine.toggleClass("btn-primary", on).toggleClass("btn-default", !on);
			mine.attr("aria-pressed", on).text(on ? `${__("My tasks")} ✕` : __("My tasks"));
			total.text(__("{0} tasks", [listview.data.length]));
			draw_cards(listview);
			if (!is_touch()) return;
			sync_tabs(listview, tabs);
			scroll.mark();
			listview.$result.find(".kanban, .kanban-cards").each(function () {
				Sortable.get(this)?.option("disabled", true);
			});
		};
		mine.on("click", async () => {
			if (is_mine()) await listview.filter_area.remove("_assign");
			else await listview.filter_area.add([[listview.doctype, "_assign", "like", `%${frappe.session.user}%`]]);
			sync();
		});
		// Opening a task hides the board, which loses its scroll, and coming back redraws
		// the columns. So the place is noted on the way out and put back after.
		let place = null;
		listview.$result.on("click", ".kb-title", () => {
			place = {
				left: listview.$result.find(".kanban").scrollLeft(),
				page: $(".main-section").scrollTop(),
				tops: {},
			};
			for (const column of listview.$result.find(".kanban-column")) {
				place.tops[column.dataset.columnValue] = $(column).find(".kanban-cards").scrollTop();
			}
		});
		const restore_place = () => {
			if (!place || !listview.$result.is(":visible")) return;
			listview.$result.find(".kanban").scrollLeft(place.left);
			for (const column of listview.$result.find(".kanban-column")) {
				$(column).find(".kanban-cards").scrollTop(place.tops[column.dataset.columnValue] || 0);
			}
			scroll.mark();
			if (is_touch()) $(".main-section").scrollTop(place.page);
			clearTimeout(place.timer);
			place.timer = setTimeout(() => (place = null), 1000);
		};
		// The board redraws its columns on every refresh, which brings back the desk's
		// cards and new drag handlers.
		new MutationObserver(() => {
			sync();
			restore_place();
		}).observe(listview.$result.get(0), { childList: true, subtree: true });
		// Scroll doesn't bubble. Only the board's own matters, so a page scroll costs nothing.
		document.addEventListener("scroll", (e) => {
			if (!is_touch() || !scroll.is_board(e.target)) return;
			sync_tabs(listview, tabs);
			scroll.swiped();
		}, { capture: true, passive: true });
		$(window).on("resize", () => is_touch() && sync_tabs(listview, tabs));
		sync();
	}

	function setup_board(listview) {
		if (listview.kiluth_bar) return;
		add_styles();
		$(document.documentElement).toggleClass("kb-touch", is_touch());
		listview.page.set_title(frappe.is_mobile() ? __("Tasks") : __("Task Board")); // a phone cuts the longer one
		kiluth.tasks.tall_controls(listview.page);
		setup_bar(listview);
		frappe.db.get_list("Project", { fields: ["name", "project_name", "customer"], limit: 0 }).then((rows) => {
			// Client first: on a phone the end of this label is what gets cut off.
			for (const row of rows) project_names[row.name] = row.customer ? `${row.customer} · ${row.project_name}` : row.project_name;
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
