/**
 * Task Waterfall: each project's tasks in dependency order, left to right.
 * Layout comes from the server (utils/task_chain.py); this file only draws it.
 * Filters: My tasks dims everyone else's, so a chain still reads end to end.
 */

const TW = { CARD: 236, GAP: 56, ROW: 54, HEIGHT: 42 };
const TW_STATUS = {
	Open: "var(--gray-500)",
	Working: "var(--blue-500)",
	"Pending Review": "var(--orange-500)",
	Overdue: "var(--red-500)",
	Completed: "var(--green-500)",
	Cancelled: "var(--gray-400)",
};

frappe.pages["task-waterfall"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Task Waterfall"), single_column: true });
	const state = { mine: false, finished: false, project: "", data: null };

	const mine = page.add_field({
		fieldname: "mine", label: __("My tasks"), fieldtype: "Check",
		change: () => { state.mine = !!mine.get_value(); draw(page, state); },
	});
	const finished = page.add_field({
		fieldname: "finished", label: __("Show finished"), fieldtype: "Check",
		change: () => { state.finished = !!finished.get_value(); load(page, state); },
	});
	state.projectField = page.add_field({
		fieldname: "project", label: __("Project"), fieldtype: "Select", options: [""],
		change: () => { state.project = state.projectField.get_value() || ""; draw(page, state); },
	});
	page.set_secondary_action(__("Refresh"), () => load(page, state));

	if (!document.getElementById("task-waterfall-css")) {
		$(`<style id="task-waterfall-css">${tw_css()}</style>`).appendTo("head");
	}
	state.root = $(`<div class="tw-root"></div>`).appendTo(page.body);
	load(page, state);
};

function load(page, state) {
	frappe.call({
		method: "kiluth_portal.kiluth_hr.page.task_waterfall.task_waterfall.get_data",
		args: { show_finished: state.finished ? 1 : 0 },
		freeze: false,
		callback: (r) => {
			state.data = r.message;
			const options = [""].concat(r.message.projects.map((p) => p.project).filter(Boolean));
			state.projectField.df.options = options;
			state.projectField.refresh();
			if (state.project) state.projectField.set_input(state.project);
			draw(page, state);
		},
	});
}

function draw(page, state) {
	const { projects, people, me } = state.data;
	const root = state.root.empty();
	root.append(tw_legend());
	let shown = 0;
	for (const p of projects) {
		if (state.project && p.project !== state.project) continue;
		const isMine = (name) => p.tasks[name].assignees.includes(me);
		if (state.mine && !Object.keys(p.tasks).some(isMine)) continue;
		shown += 1;
		root.append(tw_project(p, people, state.mine ? isMine : null));
	}
	if (!shown) root.append(`<div class="tw-empty">${__("No tasks here.")}</div>`);
}

function tw_legend() {
	const items = Object.entries(TW_STATUS)
		.map(([s, c]) => `<span class="tw-key"><i style="background:${c}"></i>${__(s)}</span>`)
		.join("");
	return `<div class="tw-legend">${items}<span class="tw-hint">${__("Left blocks right. Hover a task to see its chain.")}</span></div>`;
}

function tw_card(p, name, people, dim) {
	const t = p.tasks[name];
	const who = t.assignees.map((a) => frappe.utils.escape_html(people[a] || a)).join(", ");
	const cls = dim && !dim(name) ? " tw-dim" : "";
	return `<a class="tw-card${cls}" data-task="${name}" href="/desk/task/${encodeURIComponent(name)}"
		title="${frappe.utils.escape_html(t.subject)} (${frappe.utils.escape_html(t.status)})"
		style="border-left-color:${TW_STATUS[t.status] || "var(--gray-400)"}">
		<span class="tw-subject">${frappe.utils.escape_html(t.subject)}</span>
		<span class="tw-meta">${name} · ${who || __("Nobody")}</span>
	</a>`;
}

function tw_project(p, people, dim) {
	const title = p.project ? `${p.project} ${frappe.utils.escape_html(p.title)}` : __("No project");
	const head = `<div class="tw-head">${title}<span class="tw-count">${Object.keys(p.tasks).length}</span></div>`;
	const sec = $(`<section class="tw-project">${head}</section>`);
	if (p.chain.length) {
		const at = {};
		for (const c of p.chain) at[c.task] = c;
		const columns = Math.max(...p.chain.map((c) => c.level)) + 1;
		const width = columns * TW.CARD + (columns - 1) * TW.GAP;
		const height = p.chain.length * TW.ROW;
		const x = (c) => c.level * (TW.CARD + TW.GAP);
		const y = (c) => c.row * TW.ROW;
		const paths = p.links.map(([a, b]) => {
			const from = at[a], to = at[b];
			const x1 = x(from) + TW.CARD, y1 = y(from) + TW.HEIGHT / 2;
			const x2 = x(to), y2 = y(to) + TW.HEIGHT / 2;
			const bend = Math.max(TW.GAP / 2, (x2 - x1) / 2);
			return `<path data-a="${a}" data-b="${b}" marker-end="url(#tw-arrow)"
				d="M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}"></path>`;
		}).join("");
		const cards = p.chain.map((c) =>
			`<div class="tw-slot" style="left:${x(c)}px;top:${y(c)}px">${tw_card(p, c.task, people, dim)}</div>`
		).join("");
		const box = $(`<div class="tw-scroll"><div class="tw-canvas" style="width:${width}px;height:${height}px">
			<svg width="${width}" height="${height}"><defs><marker id="tw-arrow" viewBox="0 0 8 8" refX="7" refY="4"
				markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L8 4 L0 8 z"></path></marker></defs>${paths}</svg>
			${cards}</div></div>`);
		tw_hover(box, p);
		sec.append(box);
	}
	if (p.loose.length) {
		sec.append(`<div class="tw-loose-label">${__("Not in a chain")}</div>`);
		sec.append(`<div class="tw-loose">${p.loose.map((n) => tw_card(p, n, people, dim)).join("")}</div>`);
	}
	return sec;
}

// Hovering a task lights the tasks before and after it, and fades the rest.
function tw_hover(box, p) {
	const walk = (start, next) => {
		const seen = new Set([start]);
		const stack = [start];
		while (stack.length) {
			for (const n of next(stack.pop())) if (!seen.has(n)) { seen.add(n); stack.push(n); }
		}
		return seen;
	};
	const after = (t) => p.links.filter(([a]) => a === t).map(([, b]) => b);
	const before = (t) => p.links.filter(([, b]) => b === t).map(([a]) => a);
	box.on("mouseenter focusin", ".tw-card", function () {
		const t = this.dataset.task;
		const lit = new Set([...walk(t, after), ...walk(t, before)]);
		box.addClass("tw-tracing");
		box.find(".tw-card").each(function () { this.classList.toggle("tw-lit", lit.has(this.dataset.task)); });
		box.find("svg path[data-a]").each(function () {
			this.classList.toggle("tw-lit", lit.has(this.dataset.a) && lit.has(this.dataset.b));
		});
	});
	box.on("mouseleave focusout", ".tw-card", () => {
		box.removeClass("tw-tracing");
		box.find(".tw-lit").removeClass("tw-lit");
	});
}

function tw_css() {
	return `
	.tw-root { padding: 8px 4px 40px; display: flex; flex-direction: column; gap: 28px; }
	.tw-legend { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; font-size: 12px; color: var(--text-muted); }
	.tw-key { display: inline-flex; align-items: center; gap: 6px; }
	.tw-key i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
	.tw-hint { margin-left: auto; }
	.tw-head { font-weight: 600; font-size: 14px; color: var(--text-color); margin-bottom: 10px; display: flex; gap: 8px; align-items: baseline; }
	.tw-count { font-weight: 400; font-size: 12px; color: var(--text-muted); }
	.tw-scroll { overflow-x: auto; padding-bottom: 6px; }
	.tw-canvas { position: relative; }
	.tw-canvas svg { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
	.tw-canvas svg path[data-a] { fill: none; stroke: var(--gray-400); stroke-width: 1.4; }
	.tw-canvas marker path { fill: var(--gray-400); }
	.tw-slot { position: absolute; width: ${TW.CARD}px; }
	.tw-card { display: flex; flex-direction: column; justify-content: center; gap: 1px; height: ${TW.HEIGHT}px; padding: 0 10px; min-width: 0;
		background: var(--card-bg, var(--fg-color)); color: var(--text-color); border: 1px solid var(--border-color); border-left: 4px solid; border-radius: 6px;
		text-decoration: none; }
	.tw-card:hover { text-decoration: none; box-shadow: var(--shadow-sm); }
	.tw-subject, .tw-meta { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tw-subject { font-size: 13px; }
	.tw-meta { font-size: 11px; color: var(--text-muted); }
	.tw-dim { opacity: .35; }
	.tw-tracing .tw-card:not(.tw-lit) { opacity: .25; }
	.tw-tracing svg path[data-a]:not(.tw-lit) { opacity: .15; }
	.tw-tracing svg path.tw-lit { stroke: var(--text-color); stroke-width: 2; }
	.tw-loose-label { font-size: 12px; color: var(--text-muted); margin: 12px 0 6px; }
	.tw-loose { display: grid; grid-template-columns: repeat(auto-fill, minmax(${TW.CARD}px, 1fr)); gap: 8px; }
	.tw-empty { color: var(--text-muted); padding: 24px 0; }`;
}
