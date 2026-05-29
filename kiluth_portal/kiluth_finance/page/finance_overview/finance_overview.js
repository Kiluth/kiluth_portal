/**
 * Finance Overview — visual dashboard of Kiluth's lifetime financial state.
 *
 * Two sections matching Poom's reference design:
 *   1. Data Collected — raw numbers as horizontal bars sized by amount
 *   2. Interpretation — same numbers grouped to show "where we are" vs "goal"
 *
 * Backend at kiluth_portal.kiluth_finance.page.finance_overview.finance_overview
 * returns lifetime KPIs = (1 May 2026 snapshot) + (live GL delta since).
 */

frappe.pages["finance-overview"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Finance Overview"),
		single_column: true,
	});

	page.set_indicator(__("Loading…"), "grey");
	$(page.body).html(
		`<div id="kf-overview-root" style="padding: 24px 32px;">
			<div style="color: #888; font-family: -apple-system, system-ui, sans-serif;">Loading…</div>
		</div>`
	);

	page.set_primary_action(__("Refresh"), () => load(page));
	load(page);
};

function load(page) {
	frappe.call({
		method:
			"kiluth_portal.kiluth_finance.page.finance_overview.finance_overview.get_finance_overview",
		callback: (r) => {
			if (r.message) {
				render(r.message, page);
			}
		},
	});
}

/** Format a THB amount: "฿ 444,858.50" */
function fmt(v) {
	const n = Number(v || 0);
	return (
		"฿ " +
		n.toLocaleString("en-US", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		})
	);
}

/** Build one bar segment with proportional flex-grow. */
function bar(label, value, color, textColor) {
	const tc = textColor || "#ffffff";
	const v = Number(value || 0);
	return `<div class="kf-bar"
				style="flex: ${v}; background: ${color}; color: ${tc};">
		<div class="kf-bar-label">${label}</div>
		<div class="kf-bar-value">${fmt(v)}</div>
	</div>`;
}

/** Build a bar row that's left-aligned (one or more bars + an empty spacer). */
function row(bars, totalScale) {
	const used = bars.reduce((s, b) => s + Number(b.value || 0), 0);
	const spacer = Math.max(0, totalScale - used);
	const segments = bars
		.map((b) => bar(b.label, b.value, b.color, b.textColor))
		.join("");
	return `<div class="kf-row">
		${segments}
		${spacer > 0 ? `<div class="kf-spacer" style="flex: ${spacer};"></div>` : ""}
	</div>`;
}

function render(d, page) {
	const freshnessNote =
		d.days_since_snapshot === 0
			? "Snapshot is today."
			: `${d.days_since_snapshot} day${d.days_since_snapshot === 1 ? "" : "s"} since the last true-up.`;

	const freshnessClass =
		d.days_since_snapshot <= 7
			? "fresh"
			: d.days_since_snapshot <= 31
				? "stale-warn"
				: "stale-bad";

	page.set_indicator(
		freshnessClass === "fresh" ? __("Fresh") : __("Drifting"),
		freshnessClass === "fresh" ? "green" : freshnessClass === "stale-warn" ? "orange" : "red"
	);

	// Scale all bars to the largest aggregate — Total Expense — so proportions
	// across rows are visually consistent. If the milestone target exceeds it,
	// fall back to that (so the "Next Milestone" bar isn't cut off).
	const dataScale = Math.max(d.total_paid_out, d.money_kiluth_made, d.still_owes_poom);
	const interpScale = Math.max(dataScale, d.next_milestone_target);

	const html = `
	<style>
		#kf-overview-root {
			font-family: -apple-system, system-ui, "Inter", sans-serif;
			padding: 24px 32px 64px;
			color: #1a1a1a;
			background: #fafafa;
		}
		.kf-meta {
			color: #666;
			font-size: 12px;
			margin: 4px 0 24px;
			line-height: 1.5;
		}
		.kf-meta .kf-tag {
			display: inline-block;
			padding: 2px 8px;
			border-radius: 4px;
			font-weight: 600;
			margin-right: 6px;
		}
		.kf-meta .kf-tag.fresh { background: #d4f4dd; color: #1b5e20; }
		.kf-meta .kf-tag.stale-warn { background: #fff3cd; color: #856404; }
		.kf-meta .kf-tag.stale-bad { background: #f8d7da; color: #721c24; }

		.kf-section-title {
			font-size: 28px;
			font-weight: 700;
			margin: 40px 0 4px;
			color: #111;
		}
		.kf-section-sub {
			font-size: 11px;
			color: #888;
			margin-bottom: 16px;
		}

		.kf-row {
			display: flex;
			gap: 4px;
			margin-bottom: 4px;
			min-height: 60px;
		}
		.kf-bar {
			padding: 8px 14px;
			display: flex;
			flex-direction: column;
			justify-content: center;
			min-width: 0;
			border-radius: 2px;
			overflow: hidden;
		}
		.kf-bar-label {
			font-size: 13px;
			font-weight: 500;
			line-height: 1.25;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		.kf-bar-value {
			font-size: 16px;
			font-weight: 700;
			margin-top: 2px;
		}
		.kf-spacer {
			background: transparent;
		}
	</style>

	<div class="kf-meta">
		<span class="kf-tag ${freshnessClass}">${freshnessNote}</span>
		Last true-up: <b>${d.snapshot_date}</b> &nbsp;·&nbsp;
		As of: <b>${d.as_of}</b> &nbsp;·&nbsp;
		Source: portal.kiluth.com (ERPNext, 1 May 2026 snapshot + live deltas)
	</div>

	<div class="kf-section-title">Data Collected</div>
	<div class="kf-section-sub">Raw lifetime numbers from ERPNext.</div>

	${row(
		[
			{ label: "Amount of money Kiluth returned to Poom", value: d.returned_to_poom, color: "#E74C3C" },
			{ label: "Amount of money Kiluth paid out", value: d.kiluth_paid_out, color: "#8E44AD" },
			{ label: "Amount of money Kiluth still owes Poom", value: d.still_owes_poom, color: "#2ECC71" },
		],
		dataScale
	)}

	${row(
		[
			{ label: "Total amount Poom and Kiluth paid out", value: d.total_paid_out, color: "#5DADE2" },
		],
		dataScale
	)}

	${row(
		[
			{ label: "Amount of money Kiluth made", value: d.money_kiluth_made, color: "#4ECDC4" },
		],
		dataScale
	)}

	<div class="kf-section-title">Interpretation</div>
	<div class="kf-section-sub">The same numbers, re-labeled to show progress vs. break-even and stretch goal.</div>

	${row(
		[
			{ label: "Total Expense", value: d.total_paid_out, color: "#3F51B5" },
		],
		interpScale
	)}

	${row(
		[
			{ label: "Total Sales", value: d.money_kiluth_made, color: "#F5C400" },
			{ label: "Remaining Goal", value: d.still_owes_poom, color: "#F5E6A0", textColor: "#3a3a1a" },
			{ label: "Next Milestone", value: Math.max(0, d.next_milestone_target - d.money_kiluth_made - d.still_owes_poom), color: "#5BC76A" },
		],
		interpScale
	)}

	${row(
		[
			{ label: "Returned to Investor", value: d.returned_to_poom, color: "#E74C3C" },
			{ label: "Spent by Kiluth", value: d.kiluth_paid_out, color: "#FDEBD0", textColor: "#5a3a1a" },
		],
		interpScale
	)}
	`;

	$("#kf-overview-root").html(html);
}
