// Desk-wide navigation tweaks (loaded via hooks.py -> app_include_js).
// ERPNext v16's new desk is a left-sidebar UI (no top navbar), so the
// classic `.navbar-brand` approach doesn't apply. We hook into the sidebar
// structure instead to give users a 1-click path back to the tiled portal.
(function () {
	const PORTAL_HREF = "/";
	const PORTAL_LABEL = "Portal";
	const SIDEBAR_BTN_ID = "kiluth-portal-sidebar-link";
	const HEADER_LINK_MARK = "kiluthHeaderLinked";
	const NAVBAR_HOME_MARK = "kiluthNavbarHomeLinked";

	function makeHeaderClickable() {
		const header = document.querySelector(".sidebar-header");
		if (!header || header.dataset[HEADER_LINK_MARK] === "1") return;
		header.dataset[HEADER_LINK_MARK] = "1";
		header.style.cursor = "pointer";
		header.title = "Back to Portal";
		header.addEventListener("click", (e) => {
			if (e.target.closest("button, a, input, [role='button']")) return;
			window.location.href = PORTAL_HREF;
		});
	}

	// The top-left Kiluth wordmark lives in .navbar-home (always visible, even
	// on /desk where the sidebar collapses to zero width and hides the sidebar
	// Portal link). Make it the primary "back to Portal" affordance.
	function makeNavbarHomeClickable() {
		const home = document.querySelector(".navbar-home");
		if (!home || home.dataset[NAVBAR_HOME_MARK] === "1") return;
		home.dataset[NAVBAR_HOME_MARK] = "1";
		home.style.cursor = "pointer";
		home.title = "Back to Portal";
		home.addEventListener("click", () => {
			window.location.href = PORTAL_HREF;
		});
	}

	function ensurePortalSidebarLink() {
		if (document.getElementById(SIDEBAR_BTN_ID)) return;
		const top = document.querySelector(".body-sidebar-top")
			|| document.querySelector(".standard-items-sections")
			|| document.querySelector(".body-sidebar");
		if (!top) return;

		const link = document.createElement("a");
		link.id = SIDEBAR_BTN_ID;
		link.href = PORTAL_HREF;
		link.className = "standard-sidebar-item";
		link.style.cssText =
			"display:flex;align-items:center;gap:8px;padding:6px 12px;margin:4px 8px;border-radius:6px;cursor:pointer;color:inherit;text-decoration:none;font-size:0.9em;";
		link.innerHTML =
			'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>' +
			PORTAL_LABEL +
			"</span>";
		top.insertBefore(link, top.firstChild);
	}

	function apply() {
		makeHeaderClickable();
		makeNavbarHomeClickable();
		ensurePortalSidebarLink();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", apply);
	} else {
		apply();
	}
	if (typeof frappe !== "undefined" && frappe.router && frappe.router.on) {
		frappe.router.on("change", () => setTimeout(apply, 50));
	}
	const mo = new MutationObserver(() => apply());
	mo.observe(document.body, { childList: true, subtree: true });
})();
