// Past notifications on a phone (loaded via hooks.py -> app_include_js).
// The desk keeps them behind "Notification" in the sidebar, and on a phone that
// panel draws inside the closed sidebar, so nothing shows (Poom, 2026-11-06). The
// menu button carries the unread count (the sidebar item has the desk's own), and
// "Notification" opens the latest as a sheet instead; tapping one marks it read and opens what it's about. A bell of
// its own beside search squeezed a list page's title out. Same list as the desk's:
// Notification Log, which task_notify's "bell" channel adds comments to.
// A mouse-sized screen keeps the desk's own panel.
(function () {
	const LOG = "frappe.desk.doctype.notification_log.notification_log";
	const SHOWN = 20;

	function add_styles() {
		if (document.getElementById("kiluth-bell-css")) return;
		$(`<style id="kiluth-bell-css">
			.kn-count { display: none; }
			@media (max-width: 767px), (pointer: coarse) {
				.page-head .sidebar-toggle-btn:has(.kn-count) { position: relative; overflow: visible; }
				.kn-count.kn-on { display: inline-block; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px;
					background: var(--red-600, #e03636); color: #fff; font-size: 11px; font-weight: 600; line-height: 18px; text-align: center; }
				.sidebar-toggle-btn .kn-count.kn-on { position: absolute; top: 2px; right: -2px; }
			}
			.kn-backdrop { position: fixed; inset: 0; z-index: 1050; background: rgba(0, 0, 0, 0.5); }
			.kn-sheet { position: fixed; z-index: 1051; left: 0; right: 0; bottom: 0; max-width: 480px; max-height: 80dvh; margin: 0 auto;
				display: flex; flex-direction: column; padding: 16px 16px calc(16px + env(safe-area-inset-bottom, 0px));
				border-radius: 16px 16px 0 0; background: var(--card-bg, var(--fg-color)); color: var(--text-color);
				box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3); }
			.kn-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
			.kn-head h2 { margin: 0; font-size: 16px; font-weight: 600; }
			.kn-head button, .kn-close { min-height: 44px; padding: 0 8px; border: 0; background: transparent; color: var(--text-muted); font-size: 14px; }
			.kn-list { overflow-y: auto; overscroll-behavior: contain; }
			.kn-item { display: block; width: 100%; padding: 10px 12px; border: 0; border-radius: 10px; background: transparent;
				color: var(--text-color); text-align: left; }
			.kn-item:hover, .kn-item:focus-visible { background: var(--control-bg); outline: none; }
			.kn-item[data-unread="1"] .kn-subject { font-weight: 600; }
			.kn-item[data-unread="1"] .kn-subject::before { content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 8px;
				border-radius: 50%; background: var(--blue-500, #2490ef); vertical-align: middle; }
			.kn-subject { font-size: 15px; line-height: 1.4; overflow-wrap: anywhere; }
			.kn-meta { margin-top: 2px; font-size: 13px; color: var(--text-muted); overflow-wrap: anywhere; }
			.kn-none { padding: 24px 12px; color: var(--text-muted); text-align: center; }
			.kn-close { width: 100%; margin-top: 8px; }
		</style>`).appendTo("head");
	}

	let unread = 0;

	const on_phone = () => window.matchMedia("(max-width: 767px), (pointer: coarse)").matches;

	function show_count() {
		$(".kn-count").text(unread > 99 ? "99+" : unread).toggleClass("kn-on", unread > 0)
			.attr("aria-label", __("{0} unread notifications", [unread]));
	}

	function refresh_count() {
		if (!frappe.session?.user || frappe.session.user === "Guest") return;
		frappe.db.count("Notification Log", { filters: { for_user: frappe.session.user, read: 0 } }).then((n) => {
			unread = n;
			show_count();
		});
	}

	// On the menu button of whichever page is showing. A page draws its head once,
	// so each one gets the count once.
	function add_counts() {
		$(frappe.container?.page).find(".page-head .sidebar-toggle-btn").each(function () {
			if (!$(this).children(".kn-count").length) $(`<span class="kn-count"></span>`).appendTo(this);
		});
		show_count();
	}

	function close_sheet() {
		$(".kn-backdrop, .kn-sheet").remove();
		$(document).off("keydown.knsheet");
	}

	function item_html(row) {
		const subject = frappe.utils.html2text(row.subject || "").trim() || __("Notification");
		const about = row.document_name ? `${__(row.document_type)} ${row.document_name} · ` : "";
		return `<button type="button" class="kn-item" data-name="${frappe.utils.escape_html(row.name)}" data-unread="${row.read ? 0 : 1}">
			<div class="kn-subject">${frappe.utils.escape_html(subject)}</div>
			<div class="kn-meta">${frappe.utils.escape_html(about)}${frappe.datetime.comment_when(row.creation)}</div>
		</button>`;
	}

	function open_row(row) {
		close_sheet();
		if (!row.read) {
			frappe.xcall(`${LOG}.mark_as_read`, { docname: row.name }).then(refresh_count);
		}
		if (row.document_type && row.document_name) frappe.set_route("Form", row.document_type, row.document_name);
		else if (row.link) frappe.set_route(row.link);
	}

	async function open_sheet() {
		add_styles();
		close_sheet();
		$(`<div class="kn-backdrop"></div>`).appendTo("body").on("click", close_sheet);
		const sheet = $(`<div class="kn-sheet" role="dialog" aria-modal="true" aria-label="${__("Notifications")}">
			<div class="kn-head"><h2>${__("Notifications")}</h2><button type="button" class="kn-all" hidden>${__("Mark all as read")}</button></div>
			<div class="kn-list"><div class="kn-none">${__("Loading...")}</div></div>
			<button type="button" class="kn-close">${__("Close")}</button>
		</div>`).appendTo("body");
		sheet.find(".kn-close").on("click", close_sheet);
		$(document).on("keydown.knsheet", (e) => e.key === "Escape" && close_sheet());

		const rows = await frappe.db.get_list("Notification Log", {
			filters: { for_user: frappe.session.user },
			fields: ["name", "subject", "document_type", "document_name", "link", "read", "creation"],
			order_by: "creation desc",
			limit: SHOWN,
		});
		const list = sheet.find(".kn-list");
		if (!rows.length) {
			list.html(`<div class="kn-none">${__("No notifications yet")}</div>`);
			return;
		}
		list.html(rows.map(item_html).join(""));
		list.on("click", ".kn-item", function () {
			open_row(rows.find((r) => r.name === this.dataset.name));
		});
		sheet.find(".kn-all").prop("hidden", !rows.some((r) => !r.read)).on("click", () => {
			frappe.xcall(`${LOG}.mark_all_as_read`).then(() => {
				list.find(".kn-item").attr("data-unread", 0);
				sheet.find(".kn-all").prop("hidden", true);
				refresh_count();
			});
		});
	}

	// Before the desk's own handler, which opens the panel nothing shows of.
	document.addEventListener("click", (e) => {
		if (!on_phone() || !e.target.closest?.(".sidebar-notification")) return;
		e.preventDefault();
		e.stopImmediatePropagation();
		frappe.app.sidebar?.close();
		open_sheet();
	}, true);

	$(document).on("app_ready", () => {
		add_styles();
		refresh_count();
		frappe.realtime.on("notification", refresh_count);
	});
	// After the page shows: a list or form draws its head on the way in.
	$(document).on("page-change", () => setTimeout(add_counts));
})();
