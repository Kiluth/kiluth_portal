// Two taps iPhone got wrong (loaded via hooks.py -> app_include_js, before the
// other bundles so it sees a click first). Poom, 2026-11-07.
//
// A tap that stops a scroll only stops it. The desk scrolls inside `.main-section`,
// not the page, and on iPhone a finger that stops an inner scroller still gets a
// click, so the task under it opened. A touch that lands while scroll events are
// still coming in (the list is moving) drops the click that follows.
//
// One tap opens Notification. On a phone the desk's sidebar holds a chevron button
// that only shows while the sidebar is hovered. A finger hovers, the button shows,
// and iPhone spends that first tap on hover instead of a click. Every first tap in
// a freshly opened sidebar had this; Notification was the one that showed it.
// A screen with no hover never shows the button.
(function () {
	// Momentum fires a scroll event every frame; this is several frames.
	const MOVING_MS = 150;
	// Long enough for the click iPhone sends after the finger lifts.
	const CLICK_MS = 1000;

	let last_scroll = -Infinity;
	let drop_click_until = -Infinity;

	// Scroll doesn't bubble; capture sees every scroller's.
	document.addEventListener("scroll", () => (last_scroll = performance.now()), { capture: true, passive: true });

	document.addEventListener("touchstart", (e) => {
		const now = performance.now();
		drop_click_until = e.touches.length === 1 && now - last_scroll < MOVING_MS ? now + CLICK_MS : -Infinity;
	}, { capture: true, passive: true });

	document.addEventListener("click", (e) => {
		if (performance.now() > drop_click_until) return;
		drop_click_until = -Infinity;
		e.preventDefault();
		e.stopImmediatePropagation();
	}, true);

	if (!document.getElementById("kiluth-touch-css")) {
		const style = document.createElement("style");
		style.id = "kiluth-touch-css";
		style.textContent = `@media (hover: none) {
			.body-sidebar:hover .sidebar-toggle-btn { opacity: 0; visibility: hidden; }
		}`;
		document.head.appendChild(style);
	}
})();
