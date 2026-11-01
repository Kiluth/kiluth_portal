/**
 * Task Waterfall (Poom, 2026-11-01): each project's tasks in dependency order.
 * Layout comes from the server (utils/task_chain.py); this file only draws it.
 * A wide screen reads left to right. A phone reads top to bottom, step by step,
 * because a chain doesn't fit across one.
 * Tapping a task lights its chain and offers Open, so a chain can be read on a
 * screen with no hover. My tasks dims everyone else's, so a chain still reads end
 * to end.
 */

const TW = { CARD: 248, GAP: 56, ROW: 76, HEIGHT: 64 };
const TW_STATUS = {
	Open: "var(--gray-500)",
	Working: "var(--blue-500)",
	"Pending Review": "var(--orange-500)",
	Overdue: "var(--red-500)",
	Completed: "var(--green-500)",
	Cancelled: "var(--gray-400)",
};
const TW_FINISHED = ["Completed", "Cancelled"];
const TW_KEY = "kiluth-task-waterfall";
const tw_esc = frappe.utils.escape_html;
const tw_is_phone = () => window.innerWidth < 768;

// Remembered per person on this device. Private windows can refuse storage.
function tw_saved() {
	try {
		return JSON.parse(localStorage.getItem(TW_KEY)) || {};
	} catch {
		return {};
	}
}

function tw_save(state) {
	try {
		localStorage.setItem(TW_KEY, JSON.stringify({ mine: state.mine, folded: [...state.folded] }));
	} catch {
		// the page works without it
	}
}

frappe.pages["task-waterfall"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Task Waterfall"), single_column: true });
	const saved = tw_saved();
	const state = { mine: !!saved.mine, finished: false, project: "", folded: new Set(saved.folded || []), data: null, shown: [], phone: tw_is_phone() };
	page.add_menu_item(__("Refresh"), () => tw_load(state));

	if (!document.getElementById("task-waterfall-css")) {
		$(`<style id="task-waterfall-css">${tw_css()}</style>`).appendTo("head");
	}
	const bar = $(`<div class="tw-bar">
		<button type="button" class="tw-chip tw-mine">${__("My tasks")}</button>
		<button type="button" class="tw-chip tw-finished">${__("Show finished")}</button>
		<select class="tw-chip tw-project-pick" aria-label="${__("Project")}"></select>
	</div>`).appendTo(page.body);
	state.bar = bar;
	state.root = $(`<div class="tw-root"></div>`).appendTo(page.body);
	state.pick = $(`<div class="tw-pick" hidden>
		<div class="tw-pick-text"><div class="tw-pick-title"></div><div class="tw-pick-meta"></div></div>
		<a class="tw-pick-open btn btn-primary btn-sm">${__("Open")}</a>
		<button type="button" class="tw-pick-close" aria-label="${__("Close")}">✕</button>
	</div>`).appendTo(page.body);

	bar.find(".tw-mine").on("click", () => {
		state.mine = !state.mine;
		tw_save(state);
		tw_draw(state);
	});
	bar.find(".tw-finished").on("click", () => {
		state.finished = !state.finished;
		tw_load(state);
	});
	bar.find(".tw-project-pick").on("change", function () {
		state.project = this.value;
		tw_draw(state);
	});
	state.pick.find(".tw-pick-close").on("click", () => tw_clear_pick(state));
	$(document).on("keydown", (e) => e.key === "Escape" && tw_clear_pick(state));
	state.root.on("click", ".tw-card", function (e) {
		if (e.metaKey || e.ctrlKey || e.shiftKey) return; // a new tab, as any link
		e.preventDefault();
		e.stopPropagation(); // the desk routes every link it sees reach the body
		tw_pick(state, this);
	});
	state.root.on("click", ".tw-head", function () {
		const key = this.dataset.project;
		if (state.folded.has(key)) state.folded.delete(key);
		else state.folded.add(key);
		tw_save(state);
		tw_draw(state);
	});
	$(window).on("resize", frappe.utils.debounce(() => {
		if (tw_is_phone() === state.phone || !state.data) return;
		state.phone = tw_is_phone();
		tw_draw(state);
	}, 200));
	tw_load(state);
};

function tw_load(state) {
	frappe.call({
		method: "kiluth_portal.kiluth_hr.page.task_waterfall.task_waterfall.get_data",
		args: { show_finished: state.finished ? 1 : 0 },
		freeze: false,
		callback: (r) => {
			state.data = r.message;
			const select = state.bar.find(".tw-project-pick").empty().append(`<option value="">${__("All projects")}</option>`);
			for (const p of r.message.projects) {
				if (p.project) select.append($("<option>").val(p.project).text(tw_title(p)));
			}
			if (!r.message.projects.some((p) => p.project === state.project)) state.project = "";
			select.val(state.project);
			tw_draw(state);
		},
	});
}

function tw_title(p) {
	if (!p.project) return __("No project");
	return p.client ? `${p.client} · ${p.title}` : p.title;
}

function tw_draw(state) {
	const { projects, people, me } = state.data;
	tw_clear_pick(state);
	state.bar.find(".tw-mine").attr("aria-pressed", state.mine);
	state.bar.find(".tw-finished").attr("aria-pressed", state.finished);
	const root = state.root.empty();
	root.append(`<div class="tw-hint">${state.phone ? __("Each step waits for the one above it. Tap a task to see its chain.") : __("Left blocks right. Click a task to see its chain.")}</div>`);
	state.shown = [];
	for (const p of projects) {
		if (state.project && p.project !== state.project) continue;
		const is_mine = (name) => p.tasks[name].assignees.includes(me);
		if (state.mine && !Object.keys(p.tasks).some(is_mine)) continue;
		state.shown.push(p);
		root.append(tw_project(p, state, people, state.mine ? is_mine : null));
	}
	if (!state.shown.length) root.append(`<div class="tw-empty">${__("No tasks here.")}</div>`);
}

function tw_card(p, name, people, dim) {
	const t = p.tasks[name];
	const who = t.assignees.map((a) => people[a] || a).join(", ") || __("Nobody");
	const late = t.due && t.due < frappe.datetime.get_today() && !TW_FINISHED.includes(t.status);
	const due = t.due ? `<span class="${late ? "tw-late" : ""}">${late ? __("Late") + " · " : ""}${tw_esc(moment(t.due).format("D MMM"))}</span>` : "";
	const urgent = ["High", "Urgent"].includes(t.priority) ? `<span class="tw-urgent">${tw_esc(__(t.priority))}</span>` : "";
	return `<a class="tw-card${dim && !dim(name) ? " tw-dim" : ""}" data-task="${tw_esc(name)}" title="${tw_esc(t.subject)}" href="/desk/task/${encodeURIComponent(name)}"
		style="--tw-color:${TW_STATUS[t.status] || "var(--gray-400)"}">
		<span class="tw-subject">${tw_esc(t.subject)}</span>
		<span class="tw-meta"><span class="tw-status">${tw_esc(__(t.status))}</span>${urgent}<span class="tw-who">${tw_esc(who)}</span>${due}</span>
	</a>`;
}

function tw_canvas(p, state, people, dim) {
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
	tw_hover(box, p, state);
	return box;
}

// Tasks joined by links, one group per separate chain.
function tw_groups(p) {
	const group = {};
	const find = (t) => (group[t] === t ? t : (group[t] = find(group[t])));
	for (const c of p.chain) group[c.task] = c.task;
	for (const [a, b] of p.links) group[find(a)] = find(b);
	const groups = new Map();
	for (const c of p.chain) {
		const key = find(c.task);
		if (!groups.has(key)) groups.set(key, []);
		groups.get(key).push(c);
	}
	return [...groups.values()];
}

// Phone: each chain top to bottom. Tasks on the same step can run side by side.
function tw_steps(p, people, dim) {
	const box = $(`<div class="tw-chains"></div>`);
	for (const chain of tw_groups(p)) {
		const steps = [...new Set(chain.map((c) => c.level))].sort((a, b) => a - b);
		box.append(`<ol class="tw-steps">${steps.map((level, i) => `<li class="tw-step">
			<span class="tw-step-n">${i + 1}</span>
			<div class="tw-step-tasks">${chain.filter((c) => c.level === level).map((c) => tw_card(p, c.task, people, dim)).join("")}</div>
		</li>`).join("")}</ol>`);
	}
	return box;
}

function tw_project(p, state, people, dim) {
	const key = p.project || "none";
	const folded = state.folded.has(key);
	const count = Object.keys(p.tasks).length;
	const sec = $(`<section class="tw-project" data-index="${state.shown.length - 1}"><button type="button" class="tw-head" data-project="${tw_esc(key)}"
		aria-expanded="${!folded}"><span class="tw-name">${tw_esc(tw_title(p))}</span><span class="tw-count">${count}</span></button></section>`);
	if (folded) return sec;
	if (p.chain.length) sec.append(state.phone ? tw_steps(p, people, dim) : tw_canvas(p, state, people, dim));
	if (p.loose.length) {
		const cards = p.loose.map((n) => tw_card(p, n, people, dim)).join("");
		sec.append(p.chain.length
			? `<details class="tw-loose-more"><summary>${__("{0} not in a chain", [p.loose.length])}</summary><div class="tw-loose">${cards}</div></details>`
			: `<div class="tw-loose">${cards}</div>`);
	}
	return sec;
}

function tw_chain_of(p, task) {
	const walk = (next) => {
		const seen = new Set([task]);
		const stack = [task];
		while (stack.length) {
			for (const n of next(stack.pop())) {
				if (!seen.has(n)) {
					seen.add(n);
					stack.push(n);
				}
			}
		}
		return seen;
	};
	return new Set([
		...walk((t) => p.links.filter(([a]) => a === t).map(([, b]) => b)),
		...walk((t) => p.links.filter(([, b]) => b === t).map(([a]) => a)),
	]);
}

function tw_light(box, lit) {
	box.addClass("tw-tracing");
	box.find(".tw-card").each(function () {
		this.classList.toggle("tw-lit", lit.has(this.dataset.task));
	});
	box.find("svg path[data-a]").each(function () {
		this.classList.toggle("tw-lit", lit.has(this.dataset.a) && lit.has(this.dataset.b));
	});
}

function tw_unlight(box) {
	box.removeClass("tw-tracing").find(".tw-lit").removeClass("tw-lit");
}

function tw_pick(state, card) {
	const sec = $(card).closest(".tw-project");
	const p = state.shown[sec.data("index")];
	const name = card.dataset.task;
	const t = p.tasks[name];
	tw_clear_pick(state);
	state.picked = true;
	tw_light(sec, tw_chain_of(p, name));
	state.pick.find(".tw-pick-title").text(t.subject);
	state.pick.find(".tw-pick-meta").text(`${name} · ${__(t.status)}`);
	state.pick.find(".tw-pick-open").attr("href", card.getAttribute("href"));
	state.pick.prop("hidden", false);
}

function tw_clear_pick(state) {
	state.picked = false;
	state.pick.prop("hidden", true);
	tw_unlight(state.root);
}

// With a mouse, resting on a task previews its chain until one is picked.
function tw_hover(box, p, state) {
	box.on("mouseenter", ".tw-card", function () {
		if (!state.picked) tw_light(box, tw_chain_of(p, this.dataset.task));
	});
	box.on("mouseleave", ".tw-card", () => state.picked || tw_unlight(box));
}

function tw_css() {
	return `
	.tw-bar { position: sticky; top: var(--page-head-height, 48px); z-index: 5; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
		padding: 8px 4px; background: var(--bg-color); }
	.tw-chip { min-height: 32px; padding: 0 12px; border: 1px solid var(--border-color); border-radius: 999px; background: transparent;
		color: var(--text-color); font-size: 13px; max-width: 100%; }
	.tw-chip[aria-pressed="true"] { background: var(--text-color); border-color: var(--text-color); color: var(--bg-color); font-weight: 600; }
	select.tw-chip { flex: 0 1 280px; min-width: 0; height: 32px; text-overflow: ellipsis; }
	.tw-root { padding: 0 4px 96px; display: flex; flex-direction: column; gap: 20px; }
	.tw-hint { font-size: 12px; color: var(--text-muted); }
	.tw-head { all: unset; display: flex; gap: 8px; align-items: baseline; width: 100%; min-height: 32px; box-sizing: border-box; cursor: pointer;
		font-weight: 600; font-size: 14px; color: var(--text-color); margin-bottom: 8px; }
	.tw-head::before { content: "▾"; font-size: 11px; color: var(--text-muted); }
	.tw-head[aria-expanded="false"]::before { content: "▸"; }
	.tw-head:focus-visible { outline: 2px solid var(--border-color); outline-offset: 2px; border-radius: 6px; }
	.tw-name { min-width: 0; overflow-wrap: anywhere; }
	.tw-count { font-weight: 400; font-size: 12px; color: var(--text-muted); }
	.tw-scroll { overflow-x: auto; padding-bottom: 6px; }
	.tw-canvas { position: relative; }
	.tw-canvas svg { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
	.tw-canvas svg path[data-a] { fill: none; stroke: var(--gray-400); stroke-width: 1.4; }
	.tw-canvas marker path { fill: var(--gray-400); }
	.tw-slot { position: absolute; width: ${TW.CARD}px; }
	.tw-card { display: flex; flex-direction: column; justify-content: center; gap: 3px; min-height: ${TW.HEIGHT}px; padding: 8px 12px; min-width: 0; box-sizing: border-box;
		background: var(--card-bg, var(--fg-color)); color: var(--text-color); border: 1px solid var(--border-color); border-left: 4px solid var(--tw-color); border-radius: 8px;
		text-decoration: none; }
	.tw-slot .tw-card { height: ${TW.HEIGHT}px; }
	.tw-card:hover { color: var(--text-color); text-decoration: none; box-shadow: var(--shadow-sm); }
	.tw-subject { font-size: 13px; line-height: 1.3; }
	.tw-slot .tw-subject { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tw-meta { display: flex; flex-wrap: wrap; gap: 0 8px; font-size: 11px; color: var(--text-muted); min-width: 0; }
	.tw-slot .tw-meta { flex-wrap: nowrap; white-space: nowrap; }
	.tw-who { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
	.tw-status { flex: none; color: var(--tw-color); font-weight: 600; }
	.tw-urgent, .tw-late { flex: none; color: var(--red-600); font-weight: 600; }
	.tw-dim { opacity: .35; }
	.tw-tracing .tw-card:not(.tw-lit) { opacity: .25; }
	.tw-tracing .tw-card.tw-lit { box-shadow: 0 0 0 1px var(--text-color); }
	.tw-tracing svg path[data-a]:not(.tw-lit) { opacity: .15; }
	.tw-tracing svg path.tw-lit { stroke: var(--text-color); stroke-width: 2; }
	.tw-chains { display: flex; flex-direction: column; gap: 16px; }
	.tw-steps { list-style: none; margin: 0; padding: 0; }
	.tw-step { position: relative; display: flex; gap: 10px; padding-bottom: 10px; }
	.tw-step:not(:last-child)::before { content: ""; position: absolute; left: 11px; top: 26px; bottom: 0; width: 2px; background: var(--border-color); }
	.tw-step-n { flex: none; width: 24px; height: 24px; margin-top: 8px; border-radius: 50%; background: var(--control-bg); color: var(--text-muted); font-size: 12px;
		display: flex; align-items: center; justify-content: center; }
	.tw-step-tasks { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
	.tw-steps .tw-subject { font-size: 15px; overflow-wrap: anywhere; }
	.tw-steps .tw-meta { font-size: 12px; }
	.tw-loose-more { margin-top: 10px; font-size: 12px; color: var(--text-muted); }
	.tw-loose-more summary { min-height: 32px; display: flex; align-items: center; cursor: pointer; }
	.tw-loose { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(${TW.CARD}px, 100%), 1fr)); gap: 8px; }
	.tw-empty { color: var(--text-muted); padding: 24px 0; }
	.tw-pick { position: fixed; z-index: 20; left: 16px; right: 16px; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); max-width: 560px; margin: 0 auto;
		display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--border-color); border-radius: 12px;
		background: var(--card-bg, var(--fg-color)); box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25); }
	.tw-pick[hidden] { display: none; }
	.tw-pick-text { flex: 1; min-width: 0; }
	.tw-pick-title { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-color); }
	.tw-pick-meta { font-size: 12px; color: var(--text-muted); }
	.tw-pick-open { flex: none; }
	.tw-pick-close { flex: none; min-width: 32px; min-height: 32px; border: 0; background: transparent; color: var(--text-muted); }
	@media (max-width: 767px), (pointer: coarse) {
		.tw-chip, .tw-head, .tw-pick-open, .tw-pick-close, .tw-loose-more summary { min-height: 44px; }
		.tw-pick-open { display: inline-flex; align-items: center; padding: 0 16px; }
		.tw-pick-close { min-width: 44px; }
		.tw-bar { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
		.tw-bar::-webkit-scrollbar { display: none; }
		.tw-chip { flex: none; }
		select.tw-chip { flex: 1 0 140px; height: 44px; }
		.tw-head { align-items: center; }
	}`;
}
