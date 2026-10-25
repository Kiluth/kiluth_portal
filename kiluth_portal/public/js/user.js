// A salesperson's own planner link and QR code, shown on their user page.
// Leads that come through it go to them (utils/lead_routing.py, Poom 2026-10-25).
frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("kiluth_portal.utils.lead_routing.planner_link", { user: frm.doc.name }).then((r) => {
			const link = r.message || {};
			if (!link.url) return;
			frm.dashboard.add_section(
				`<div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
					<img src="data:image/svg+xml;base64,${link.qr}" alt="QR code for the planner link" style="width:132px;height:132px;border:1px solid var(--border-color);border-radius:8px;padding:6px;background:#fff">
					<div>
						<div style="font-weight:600;margin-bottom:4px">Your planner link</div>
						<div style="color:var(--text-muted);margin-bottom:8px">Leads who send a brief through it come straight to you.</div>
						<code style="user-select:all">${frappe.utils.escape_html(link.url)}</code>
					</div>
				</div>`,
				__("Planner link")
			);
		});
	},
});
