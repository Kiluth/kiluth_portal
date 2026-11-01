// The Task page, read from top to bottom (Poom, 2026-11-01): what it is, who has it,
// what done means, what it waits on and blocks, then comments, which are the desk's
// own footer below. Nothing is removed: every field is under "All details", which
// is the desk's own form, so editing and saving work as they always did.
(() => {
	const esc = frappe.utils.escape_html;

	function add_styles() {
		if (document.getElementById("kiluth-task-css")) return;
		$(`<style id="kiluth-task-css">
			:root { --kt-edge: var(--gray-300); --kt-high: var(--red-600); --kt-high-bg: var(--red-50); --kt-medium: var(--orange-700); --kt-medium-bg: var(--orange-50); }
			[data-theme="dark"] { --kt-edge: var(--gray-700); --kt-high: #ff9d97; --kt-high-bg: rgba(229, 72, 77, 0.2); --kt-medium: #ffc27a; --kt-medium-bg: rgba(245, 158, 11, 0.16); }
			.kt-folded .form-layout { display: none; }
			.kt-task { max-width: 760px; margin: 0 auto; padding: 12px 16px 8px; color: var(--text-color); }
			.kt-title { margin: 0; font-size: 22px; line-height: 1.25; font-weight: 600; overflow-wrap: anywhere; }
			.kt-tap { all: unset; display: inline-flex; align-items: center; gap: 6px; max-width: 100%; min-height: 32px; cursor: pointer; box-sizing: border-box; }
			@media (max-width: 767px), (pointer: coarse) { .kt-tap:not(:disabled) { min-height: 44px; } }
			.kt-tap:disabled { cursor: default; }
			.kt-tap:focus-visible { outline: 2px solid var(--kt-edge); outline-offset: 2px; border-radius: 6px; }
			.kt-tap:not(:disabled):hover { opacity: 0.8; }
			.kt-caret::after { content: "▾"; font-size: 10px; color: var(--text-muted); }
			.kt-title .kt-tap { display: block; white-space: normal; overflow-wrap: anywhere; }
			/* Changes save as they're made, so Save is only for All details. */
			.kt-saves-itself .page-actions .primary-action { display: none !important; }
			.kt-id { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 13px; color: var(--text-muted); }
			.kt-id code { padding: 0; background: none; color: inherit; font-size: 13px; user-select: all; }
			.kt-facts { margin: 16px 0 0; display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 2px 8px; align-items: center; }
			.kt-facts dt { font-weight: 400; font-size: 13px; color: var(--text-muted); }
			.kt-facts dd { margin: 0; min-height: 36px; display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 14px; flex-wrap: wrap; }
			.kt-chip { display: inline-flex; align-items: center; padding: 1px 8px; border-radius: 999px; font-size: 13px; font-weight: 600; background: var(--control-bg); color: var(--text-muted); }
			.kt-chip[data-priority="High"], .kt-chip[data-priority="Urgent"] { color: var(--kt-high); background: var(--kt-high-bg); }
			.kt-chip[data-priority="Medium"] { color: var(--kt-medium); background: var(--kt-medium-bg); }
			.kt-btn { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0 10px; border: 1px solid var(--kt-edge); border-radius: 8px;
				background: transparent; color: var(--text-color); font-size: 13px; }
			.kt-status::after { content: "▾"; font-size: 10px; color: var(--text-muted); }
			.kt-late { color: var(--kt-high); font-weight: 600; }
			.kt-person { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
			.kt-nobody { color: var(--kt-high); font-weight: 600; }
			.kt-flag { margin-top: 14px; padding: 10px 12px; border-radius: 10px; font-size: 14px; color: var(--kt-high); background: var(--kt-high-bg); white-space: pre-line; }
			.kt-section { margin-top: 20px; }
			.kt-section h2 { margin: 0 0 6px; font-size: 13px; font-weight: 600; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }
			.kt-done { display: block; width: 100%; padding: 10px 12px; border: 1px solid var(--kt-edge); border-radius: 10px; font-size: 15px; line-height: 1.45; white-space: pre-line; }
			.kt-unset { color: var(--text-muted); }
			.kt-body { font-size: 15px; line-height: 1.5; overflow-wrap: anywhere; }
			.kt-body img { max-width: 100%; height: auto; }
			.kt-link { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 40px; padding: 6px 0;
				border-top: 1px solid var(--kt-edge); color: var(--text-color); font-size: 14px; text-decoration: none; }
			.kt-link:hover { color: var(--text-color); text-decoration: none; }
			.kt-link span:first-child { min-width: 0; overflow-wrap: anywhere; }
			.kt-link .kt-s { flex: none; font-size: 12px; color: var(--text-muted); }
			.kt-none { font-size: 14px; color: var(--text-muted); }
			.kt-more { margin: 20px 0 8px; width: 100%; justify-content: center; min-height: 40px; }
			.kt-back { display: none; flex: none; align-items: center; gap: 2px; min-height: 40px; margin-right: 8px; padding: 0 10px 0 4px; border: 1px solid var(--kt-edge); border-radius: 8px;
				background: transparent; color: var(--text-color); font-size: 14px; }
			@media (max-width: 767px), (pointer: coarse) { .kt-back { display: inline-flex; } }
		</style>`).appendTo("head");
	}

	// "Done when" is a line in the description, by house rule. Show it on its own.
	const DONE_LINE = /(?:<p[^>]*>|<div[^>]*>|<br\s*\/?>|^)\s*(?:<[^>]+>\s*)*done when[\s\S]*?(?=<\/p>|<\/div>|<br|$)/i;

	function split_description(html) {
		const found = (html || "").match(DONE_LINE);
		if (!found) return { done: "", body: html || "" };
		const text = frappe.utils.html2text(found[0]).replace(/^\s*done when\b[:\s]*/i, "").trim();
		const done = text.charAt(0).toUpperCase() + text.slice(1);
		return { done, body: html.replace(found[0], "") };
	}

	// Only the Done when line changes: the rest of the description stays as it is.
	function with_done(html, done) {
		const line = `${__("Done when")}: ${esc(done.trim().replace(/\s+/g, " "))}`;
		const found = (html || "").match(DONE_LINE);
		if (!found) return `<p>${line}</p>${html || ""}`;
		const opening = found[0].match(/^(?:<p[^>]*>|<div[^>]*>|<br\s*\/?>)?/)[0];
		return html.replace(found[0], () => opening + line);
	}

	function fact(label, html) {
		return `<dt>${label}</dt><dd>${html}</dd>`;
	}

	function name_of(user) {
		return user ? esc(frappe.user_info(user).fullname || user) : "";
	}

	function assignee_html(frm) {
		const people = (frm.get_docinfo().assignments || []).map((a) => a.owner);
		const who = people.length
			? `<span class="kt-person">${frappe.avatar(people[0], "avatar-small")}<span>${name_of(people[0])}${people.length > 1 ? ` +${people.length - 1}` : ""}</span></span>`
			: `<span class="kt-nobody">${__("Nobody")}</span>`;
		return `${who}<button type="button" class="kt-btn kt-hand">${__("Hand over")}</button>`;
	}

	function due_html(frm) {
		const day = String(frm.doc.exp_end_date || "").slice(0, 10);
		if (!day) return `<span class="text-muted">${__("No date")}</span>`;
		const late = day < frappe.datetime.get_today() && !["Completed", "Cancelled"].includes(frm.doc.status);
		return `<span class="${late ? "kt-late" : ""}">${late ? __("Late") + " · " : ""}${esc(moment(day).format("D MMM YYYY"))}</span>`;
	}

	function move(frm, status) {
		if (frm.is_dirty()) {
			frappe.show_alert({ message: __("Save your changes first"), indicator: "orange" });
			return;
		}
		const from = frm.doc.status;
		const set = (value) => frm.set_value("status", value).then(() => frm.save());
		set(status).then(() => kiluth.tasks.undo_bar(__("Moved to {0}", [__(status)]), () => set(from)));
	}

	// Every change here needs a deliberate choice and Save, and comes with Undo.
	function change(frm, field, value, label) {
		if (frm.is_dirty()) {
			frappe.show_alert({ message: __("Save your changes first"), indicator: "orange" });
			return;
		}
		const task = frm.docname;
		const reload = () => frm.docname === task && frm.reload_doc();
		const set = (to, modified) => frappe.xcall("kiluth_portal.utils.task_page.set_field", { task, field, value: to, modified });
		const was = frm.doc[field] || "";
		set(value, frm.doc.modified).then(
			(modified) => {
				reload();
				kiluth.tasks.undo_bar(__("{0} changed", [label]), () => set(was, modified).then(reload, reload));
			},
			reload
		);
	}

	function ask(frm, label, field, value, df, to_value = (v) => v) {
		let saved = false; // a double tap lands while the dialog fades out
		const dialog = new frappe.ui.Dialog({
			title: __("Change {0}", [label.toLowerCase()]),
			fields: [{ fieldname: "value", label, ...df }],
			primary_action_label: __("Save"),
			primary_action(values) {
				if (saved) return;
				saved = true;
				dialog.hide();
				if ((values.value || "") !== (value || "")) change(frm, field, to_value(values.value || ""), label);
			},
		});
		dialog.set_value("value", value || "");
		dialog.show();
		dialog.$wrapper.find(".form-control").css("font-size", "16px"); // under 16px an iPhone zooms in
	}

	function setup_edits(frm, panel, title_fixed) {
		const doc = frm.doc;
		panel.find(".kt-tap").prop("disabled", false);
		panel.find(".kt-title .kt-tap").prop("disabled", title_fixed);
		frm.set_df_property("subject", "read_only", title_fixed ? 1 : 0);
		panel.find(".kt-title .kt-tap").on("click", () => ask(frm, __("Title"), "subject", doc.subject, { fieldtype: "Data", reqd: 1 }));
		panel.find(".kt-due").on("click", () => ask(frm, __("Due"), "exp_end_date", String(doc.exp_end_date || "").slice(0, 10), { fieldtype: "Date" }));
		panel.find(".kt-pri").on("click", () => kiluth.tasks.pick_one({
			head: __("Priority"),
			title: doc.subject,
			choices: frappe.meta.get_docfield("Task", "priority").options.split("\n"),
			current: doc.priority,
			done: (priority) => change(frm, "priority", priority, __("Priority")),
		}));
		panel.find(".kt-proj").on("click", () => ask(frm, __("Project"), "project", doc.project, { fieldtype: "Link", options: "Project" }));
		panel.find(".kt-done").on("click", () => ask(frm, __("Done when"), "description", split_description(doc.description).done, { fieldtype: "Small Text", reqd: 1, max_height: "120px" }, (done) => with_done(doc.description, done)));
		panel.find(".kt-desc").on("click", () => ask(frm, __("Description"), "description", doc.description, { fieldtype: "Text Editor" }));
	}

	function hand_over(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Hand over"),
			fields: [
				{
					fieldname: "to_user", label: __("Who has it next?"), fieldtype: "Link", options: "User", reqd: 1,
					get_query: () => ({ filters: { enabled: 1, user_type: "System User" } }),
					description: __("They replace the current assignee. A task has one."),
				},
			],
			primary_action_label: __("Hand over"),
			primary_action({ to_user }) {
				frappe.xcall("kiluth_portal.utils.task_page.hand_over", { task: frm.docname, to_user }).then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("Handed over to {0}", [frappe.user_info(to_user).fullname || to_user]), indicator: "green" });
					frm.reload_doc();
				});
			},
		});
		dialog.show();
	}

	// What's still open comes first: that's what matters to someone reading the task.
	function links_html(rows) {
		if (!rows.length) return `<div class="kt-none">${__("Nothing")}</div>`;
		const finished = (r) => ["Completed", "Cancelled"].includes(r.status);
		const ordered = [...rows.filter((r) => !finished(r)), ...rows.filter(finished)];
		return ordered.map((r) => `<a class="kt-link" href="${frappe.utils.get_form_link("Task", r.name)}">
			<span>${esc(r.subject)}</span><span class="kt-s">${esc(__(r.status))}</span></a>`).join("");
	}

	function set_fold(frm, folded) {
		frm.page.main.toggleClass("kt-folded", folded);
		frm.page.main.find(".kt-more").text(folded ? __("All details") : __("Hide details"));
		frm.page.wrapper.toggleClass("kt-saves-itself", folded && !frm.is_dirty());
	}

	// A phone app has no browser Back button (Poom, 2026-11-01). Going back keeps the
	// board's filter. A task opened from a link or an alert has no board behind it, so
	// this opens the one Home opens. A full load: a board's first show drops
	// route_options, so only the URL can filter it.
	function back_to_board() {
		const is_tasks = (route) => route?.[0] === "List" && route[1] === "Task";
		if (is_tasks(frappe.get_prev_route())) history.back();
		else if (frappe.route_history.some(is_tasks)) frappe.set_route("List", "Task", "Kanban", "Tasks");
		else window.location.assign("/my-board");
	}

	function add_back(frm) {
		if (frm.page.kt_back) return;
		frm.page.kt_back = $(`<button type="button" class="kt-back">${frappe.utils.icon("es-line-left-chevron", "md")}${__("Back")}</button>`)
			.insertBefore(frm.page.wrapper.find(".page-head .title-area"))
			.on("click", back_to_board);
	}

	function draw(frm) {
		add_styles();
		add_back(frm);
		frm.page.main.find(".kt-task").remove();
		if (frm.is_new()) {
			frm.page.main.removeClass("kt-folded");
			frm.page.wrapper.removeClass("kt-saves-itself");
			return;
		}
		const doc = frm.doc;
		const { done, body } = split_description(doc.description);
		const failing = doc.hygiene === "Fail" && doc.hygiene_note;
		// A finished task is a record. Controls start disabled: setup_edits turns them on
		// once the server says whether the title may change.
		const editable = frm.has_perm("write") && !["Completed", "Cancelled"].includes(doc.status);
		const panel = $(`<div class="kt-task">
			<h1 class="kt-title"><button type="button" class="kt-tap" disabled>${esc(doc.subject)}</button></h1>
			<div class="kt-id"><code>${esc(doc.name)}</code><button type="button" class="kt-btn kt-copy" aria-label="${esc(__("Copy {0}", [doc.name]))}">${__("Copy")}</button></div>
			<dl class="kt-facts">
				${fact(__("Status"), `<button type="button" class="kt-btn kt-status">${esc(__(doc.status))}</button>`)}
				${fact(__("Assignee"), assignee_html(frm))}
				${fact(__("Due"), `<button type="button" class="kt-tap kt-due ${editable ? "kt-caret" : ""}" disabled>${due_html(frm)}</button>`)}
				${fact(__("Priority"), `<button type="button" class="kt-tap kt-pri ${editable ? "kt-caret" : ""}" disabled><span class="kt-chip" data-priority="${esc(doc.priority || "")}">${esc(__(doc.priority || "Low"))}</span></button>`)}
				${fact(__("Project"), `${doc.project ? `<a class="kt-project" href="${frappe.utils.get_form_link("Project", doc.project)}">${esc(doc.project)}</a>` : `<span class="text-muted">${__("No project")}</span>`}${editable ? `<button type="button" class="kt-btn kt-proj">${__("Change")}</button>` : ""}`)}
				${doc.account_manager ? fact(__("Account Manager"), name_of(doc.account_manager)) : ""}
				${doc.project_manager ? fact(__("Project Manager"), name_of(doc.project_manager)) : ""}
			</dl>
			${failing ? `<div class="kt-flag">${esc(doc.hygiene_note)}</div>` : ""}
			${done || editable ? `<div class="kt-section"><h2>${__("Done when")}</h2><button type="button" class="kt-tap kt-done" disabled>${done ? esc(done) : `<span class="kt-unset">${__("Say what done means")}</span>`}</button></div>` : ""}
			${frappe.utils.html2text(body).trim() || editable ? `<div class="kt-section"><h2><span>${__("Description")}</span>${editable ? `<button type="button" class="kt-btn kt-desc">${__("Edit")}</button>` : ""}</h2><div class="kt-body">${frappe.utils.html2text(body).trim() ? frappe.dom.remove_script_and_style(body) : `<span class="kt-unset">${__("Nothing")}</span>`}</div></div>` : ""}
			<div class="kt-section"><h2><span>${__("Waits on")}</span><button type="button" class="kt-btn kt-deps">${__("Edit")}</button></h2><div class="kt-waits"></div></div>
			<div class="kt-section"><h2>${__("Blocks")}</h2><div class="kt-blocks"></div></div>
			<button type="button" class="kt-btn kt-more"></button>
		</div>`);
		frm.page.main.prepend(panel);
		panel.find(".kt-copy").on("click", () => frappe.utils.copy_to_clipboard(doc.name));
		panel.find(".kt-status").on("click", () => kiluth.tasks.pick_status(
			{ name: doc.name, subject: doc.subject, status: doc.status, owner: doc.owner },
			(status) => move(frm, status)
		));
		panel.find(".kt-hand").on("click", () => hand_over(frm));
		panel.find(".kt-more").on("click", () => set_fold(frm, !frm.page.main.hasClass("kt-folded")));
		panel.find(".kt-deps").on("click", () => {
			set_fold(frm, false);
			frm.scroll_to_field("depends_on");
		});
		set_fold(frm, frm.kt_open ? false : true);
		frappe.xcall("kiluth_portal.utils.task_page.links", { task: doc.name }).then((r) => {
			panel.find(".kt-waits").html(links_html(r.waits_on));
			panel.find(".kt-blocks").html(links_html(r.blocks));
			if (r.project) panel.find(".kt-project").text(r.project);
			if (editable) setup_edits(frm, panel, r.title_fixed);
		});
		// The panel says these in full; a phone cuts the title short and shows the
		// status as a bare dot. Deferred: the toolbar sets them again after this.
		setTimeout(() => {
			if (frm.docname !== doc.name) return;
			frm.page.set_title(__("Task"));
			if (!frm.is_dirty()) frm.page.clear_indicator();
		});
	}

	frappe.ui.form.on("Task", {
		refresh: draw,
		// An unsaved edit always gets its Save, whatever the page is showing.
		onload: (frm) => frm.$wrapper.on("dirty", () => frm.page.wrapper.removeClass("kt-saves-itself")),
	});
})();
