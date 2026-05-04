"""Monthly financial report — auto-emailed PDF.

Runs on the 5th of every month at 09:00 (Asia/Bangkok). Builds a multi-page
PDF (At-a-glance KPIs, Statement of Operations, Balance Sheet) and emails it
to the management@ Workspace group. Membership is managed in the Google
Workspace admin console — no code change to add/remove recipients. The cron
schedule lives in `hooks.py` under `scheduler_events`.

Design lives in this module (not a Server Script) because:
- Server Scripts need `server_script_enabled` in site_config.json which we
  deliberately leave off.
- Code in the app is version-controlled and survives redeploys.

Privacy: the underlying loan account is named after a real investor.
For the PDF we relabel it to "Loan from Investors" (NAME_REMAP).

Manual test (whitelisted; pass `recipients` to avoid hitting the group):

    await frappe.call({
        method: 'kiluth_portal.utils.financial_report.send_monthly_report',
        args: {recipients: ['poom.pengcharoen@kiluth.com']}
    })

Idempotency: each invocation builds a fresh report covering the prior
calendar month relative to "now". The scheduler won't double-fire, but
manual `bench execute` calls the same day will produce duplicate emails.

The PDF is rendered by wkhtmltopdf (Frappe default). Fonts are inlined as
base64 data URLs in @font-face — sidesteps wkhtmltopdf's flaky resolution
of file:// and remote font URLs, and survives sandboxed worker processes.
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import getdate, nowdate
from frappe.utils.pdf import get_pdf


COMPANY = "Kiluth"
CURRENCY = "฿"
# Single Google Workspace group — fan-out to humans is configured in the
# Workspace admin console, so the membership can change without a code change.
RECIPIENTS = ("management@kiluth.com",)

# Per-account relabeling for privacy. Full ERPNext account name → PDF label.
NAME_REMAP = {
	"Loan from Pavaruth Pengcharoen - K": "Loan from Investors",
}

LOAN_ACCOUNT = "Loan from Pavaruth Pengcharoen - K"

# Categorical palette — muted but distinguishable. Document chrome stays
# monochrome; data viz uses color so categories can be told apart at a glance.
PALETTE = (
	"#1a3a52",  # deep navy   (dominant category)
	"#c19a6b",  # warm tan
	"#5e8a7c",  # muted teal
	"#8a4a3a",  # terracotta
	"#6b7c93",  # slate
	"#a89880",  # stone
	"#3d3d3d",  # charcoal
	"#b5a8c9",  # dusty lavender ("Other")
)


# ─── Public entry point ─────────────────────────────────────────────────────

@frappe.whitelist()
def send_monthly_report(recipients: list[str] | str | None = None):
	"""Build and email the prior month's financial report.

	`recipients` defaults to the module-level RECIPIENTS tuple (the cron uses
	this). Manual invocations can pass a single email or a list to override —
	handy for testing without spamming the management group. Only users with
	the System Manager role can call this via the API.
	"""
	if not frappe.has_permission("Server Script", "write"):
		# Reuse Server Script perm as a proxy for "trusted enough to email
		# financial data" — System Manager has it by default.
		frappe.throw("Not permitted to send the monthly financial report.")

	# Frappe's RPC layer JSON-encodes list args when called via /api/method/...,
	# so a list passed from the browser arrives here as a JSON string. Decode
	# that case before defaulting to "single string => one-recipient list".
	if recipients is None:
		recipients = list(RECIPIENTS)
	elif isinstance(recipients, str):
		stripped = recipients.strip()
		if stripped.startswith("["):
			recipients = frappe.parse_json(stripped)
		else:
			recipients = [stripped]
		recipients = list(recipients)
	else:
		recipients = list(recipients)

	period = _compute_period()
	html = _render_html(period)
	pdf_bytes = get_pdf(html)

	subject = f"Kiluth — Monthly Financial Report — {period['label']}"
	body = _email_body(period)
	attachment = {
		"fname": f"Kiluth-Financial-Report-{period['start'].strftime('%Y-%m')}.pdf",
		"fcontent": pdf_bytes,
	}

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=body,
		attachments=[attachment],
		delayed=False,
	)
	return {"period": period["label"], "recipients": recipients}


# ─── Period setup ───────────────────────────────────────────────────────────

def _compute_period() -> dict:
	"""Prior full month relative to today."""
	today_dt = getdate(nowdate())
	first_of_this = today_dt.replace(day=1)
	last_of_prior = first_of_this - datetime.timedelta(days=1)
	period_start = last_of_prior.replace(day=1)
	period_end = last_of_prior

	# 11 calendar months back to get TTM (trailing 12mo) start.
	ttm_start = period_start
	for _ in range(11):
		ttm_start = (ttm_start - datetime.timedelta(days=1)).replace(day=1)

	return {
		"start": period_start,
		"end": period_end,
		"label": period_start.strftime("%B %Y"),
		"fy_start": period_start.replace(month=1, day=1),
		"prior_month_end": period_start - datetime.timedelta(days=1),
		"prior_month_start": (period_start - datetime.timedelta(days=1)).replace(day=1),
		"ttm_start": ttm_start,
	}


def _monthly_periods(end_date, n=12):
	"""(period_start, period_end) tuples, oldest→newest, n months ending at end_date."""
	out = []
	cur_end = end_date
	for _ in range(n):
		cur_start = cur_end.replace(day=1)
		out.append((cur_start, cur_end))
		cur_end = cur_start - datetime.timedelta(days=1)
	return list(reversed(out))


# ─── Data pulls (frappe.db.sql) ─────────────────────────────────────────────

def _sum_root(root_type: str, start, end) -> float:
	res = frappe.db.sql(
		"""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0
			AND acc.root_type = %s
			AND gle.posting_date BETWEEN %s AND %s
		""",
		(COMPANY, root_type, start, end),
	)
	return float(res[0][0] or 0)


def _account_balance_on(account: str, on_date) -> float:
	res = frappe.db.sql(
		"""
		SELECT SUM(debit - credit) FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0
			AND account = %s
			AND posting_date <= %s
		""",
		(COMPANY, account, on_date),
	)
	return float(res[0][0] or 0)


def _list_leaf_accounts(root_type: str) -> list[dict]:
	return frappe.db.sql(
		"""
		SELECT name, account_type FROM `tabAccount`
		WHERE company = %s AND is_group = 0 AND root_type = %s
		ORDER BY lft ASC
		""",
		(COMPANY, root_type),
		as_dict=True,
	)


def _gl_account_period(account: str, start, end) -> float:
	res = frappe.db.sql(
		"""
		SELECT SUM(debit - credit) FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0
			AND account = %s
			AND posting_date BETWEEN %s AND %s
		""",
		(COMPANY, account, start, end),
	)
	return float(res[0][0] or 0)


def _gl_account_monthly(account: str, start, end) -> dict:
	"""Bucket GL entries by (year, month) for one account in [start, end]."""
	rows = frappe.db.sql(
		"""
		SELECT YEAR(posting_date) AS y, MONTH(posting_date) AS m,
			SUM(debit - credit) AS amt
		FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0
			AND account = %s
			AND posting_date BETWEEN %s AND %s
		GROUP BY YEAR(posting_date), MONTH(posting_date)
		""",
		(COMPANY, account, start, end),
		as_dict=True,
	)
	return {(int(r["y"]), int(r["m"])): float(r["amt"] or 0) for r in rows}


def _cash_accounts() -> list[dict]:
	return [a for a in _list_leaf_accounts("Asset")
		if a.get("account_type") in ("Cash", "Bank")]


def _cash_balance_on(on_date) -> float:
	return sum(_account_balance_on(a["name"], on_date) for a in _cash_accounts())


def _loan_balance_on(on_date) -> float:
	# Liability — negate so it shows as a positive balance.
	return -_account_balance_on(LOAN_ACCOUNT, on_date)


# ─── Derived: 12-month series + tables ─────────────────────────────────────

def _build_monthly_series(end_date, n: int = 12) -> dict:
	"""Build per-month series we need for charts/sparklines."""
	periods = _monthly_periods(end_date, n)
	labels = [s.strftime("%b") for s, _ in periods]
	series_start = periods[0][0]

	income_accts = _list_leaf_accounts("Income")
	expense_accts = _list_leaf_accounts("Expense")

	revenue = [0.0] * n
	for a in income_accts:
		monthly = _gl_account_monthly(a["name"], series_start, end_date)
		for j, (s, _) in enumerate(periods):
			revenue[j] += -monthly.get((s.year, s.month), 0.0)

	expense_by_cat: dict[str, list[float]] = {}
	expenses_total = [0.0] * n
	for a in expense_accts:
		monthly = _gl_account_monthly(a["name"], series_start, end_date)
		amts = [monthly.get((s.year, s.month), 0.0) for s, _ in periods]
		if any(abs(x) > 0.005 for x in amts):
			expense_by_cat[_relabel(a["name"])] = amts
		for j, v in enumerate(amts):
			expenses_total[j] += v

	expense_by_cat = dict(
		sorted(expense_by_cat.items(), key=lambda kv: -sum(kv[1]))
	)

	net = [revenue[j] - expenses_total[j] for j in range(n)]
	cash = [_cash_balance_on(e) for _, e in periods]
	loan = [_loan_balance_on(e) for _, e in periods]

	return {
		"months": periods,
		"labels": labels,
		"revenue": revenue,
		"expenses": expenses_total,
		"net": net,
		"cash": cash,
		"loan": loan,
		"expense_by_cat": expense_by_cat,
	}


def _build_pl_table(periods: list) -> list:
	"""P&L combined across periods. Returns (label, [amts], indent, bold) rows.
	Uses chart-of-accounts order so rows stay stable regardless of activity.
	"""
	income_accts = _list_leaf_accounts("Income")
	expense_accts = _list_leaf_accounts("Expense")

	def amt_for(account, start, end, sign):
		return sign * _gl_account_period(account, start, end)

	income_per = []
	for a in income_accts:
		amts = [amt_for(a["name"], s, e, -1) for s, e in periods]
		if any(abs(x) > 0.005 for x in amts):
			income_per.append((a["name"], amts))

	expense_per = []
	for a in expense_accts:
		amts = [amt_for(a["name"], s, e, 1) for s, e in periods]
		if any(abs(x) > 0.005 for x in amts):
			expense_per.append((a["name"], amts))

	n = len(periods)
	income_totals = [sum(amts[i] for _, amts in income_per) for i in range(n)]
	expense_totals = [sum(amts[i] for _, amts in expense_per) for i in range(n)]
	net = [income_totals[i] - expense_totals[i] for i in range(n)]

	rows = [("Revenue", income_totals, 0, True)]
	for name, amts in income_per:
		rows.append((_relabel(name), amts, 1, False))
	rows.append(("", [None] * n, 0, False))
	rows.append(("Operating expenses", [None] * n, 0, True))
	for name, amts in expense_per:
		rows.append((_relabel(name), [-x for x in amts], 1, False))
	rows.append(("Total operating expenses", [-x for x in expense_totals], 0, True))
	rows.append(("", [None] * n, 0, False))
	rows.append(("Net profit / (loss)", net, 0, True))
	return rows


def _build_bs_table(dates: list) -> list:
	"""Balance Sheet combined across as-of dates."""
	asset_accts = _list_leaf_accounts("Asset")
	liab_accts = _list_leaf_accounts("Liability")
	equity_accts = _list_leaf_accounts("Equity")

	def per_dates(accounts, sign):
		out = []
		for a in accounts:
			amts = [sign * _account_balance_on(a["name"], d) for d in dates]
			if any(abs(x) > 0.005 for x in amts):
				out.append((a["name"], amts))
		return out

	asset_per = per_dates(asset_accts, 1)
	liab_per = per_dates(liab_accts, -1)
	equity_per = per_dates(equity_accts, -1)

	n = len(dates)
	asset_totals = [sum(amts[i] for _, amts in asset_per) for i in range(n)]
	liab_totals = [sum(amts[i] for _, amts in liab_per) for i in range(n)]
	equity_explicit_totals = [sum(amts[i] for _, amts in equity_per) for i in range(n)]

	# Accumulated P&L as implied equity.
	accum_pl = []
	earliest = datetime.date(2000, 1, 1)
	for d in dates:
		inc = -_sum_root("Income", earliest, d)
		exp = _sum_root("Expense", earliest, d)
		accum_pl.append(inc - exp)
	equity_totals = [equity_explicit_totals[i] + accum_pl[i] for i in range(n)]

	rows = [("Assets", [None] * n, 0, True)]
	for name, amts in asset_per:
		rows.append((_relabel(name), amts, 1, False))
	rows.append(("Total assets", asset_totals, 0, True))
	rows.append(("", [None] * n, 0, False))

	rows.append(("Liabilities", [None] * n, 0, True))
	for name, amts in liab_per:
		rows.append((_relabel(name), amts, 1, False))
	rows.append(("Total liabilities", liab_totals, 0, True))
	rows.append(("", [None] * n, 0, False))

	rows.append(("Equity", [None] * n, 0, True))
	for name, amts in equity_per:
		rows.append((_relabel(name), amts, 1, False))
	if any(abs(x) > 0.005 for x in accum_pl):
		rows.append(("Accumulated profit / (loss)", accum_pl, 1, False))
	rows.append(("Total equity", equity_totals, 0, True))
	return rows


# ─── Formatters / labels ────────────────────────────────────────────────────

def _relabel(account: str) -> str:
	return NAME_REMAP.get(account, account.replace(" - K", "").strip())


def _fmt(amt) -> str:
	"""Accountant style: ฿ 1,234.56 or (฿ 1,234.56) for negatives."""
	if amt is None:
		return ""
	if abs(amt) < 0.005:
		return "—"
	if amt < 0:
		return f"(฿ {abs(amt):,.2f})"
	return f"฿ {amt:,.2f}"


def _fmt_compact(v) -> str:
	"""Short money format for chart axes / KPI tiles."""
	if v is None:
		return ""
	if abs(v) >= 1_000_000:
		return f"฿{v/1_000_000:.1f}M"
	if abs(v) >= 1_000:
		return f"฿{v/1_000:.0f}K"
	return f"฿{v:.0f}"


# ─── SVG chart primitives ───────────────────────────────────────────────────

def _sparkline_svg(values, width=140, height=28, color="#1a1a1a") -> str:
	if not values:
		return ""
	vmin, vmax = min(values), max(values)
	rng = vmax - vmin or 1
	pts = " ".join(
		f"{i / max(len(values) - 1, 1) * (width - 2) + 1:.1f},"
		f"{height - 1 - (v - vmin) / rng * (height - 2):.1f}"
		for i, v in enumerate(values)
	)
	last_x = width - 1
	last_y = height - 1 - (values[-1] - vmin) / rng * (height - 2)
	return (
		f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
		f'xmlns="http://www.w3.org/2000/svg">'
		f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1"/>'
		f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="1.5" fill="{color}"/>'
		f"</svg>"
	)


def _stacked_bar_svg(categories: dict, period_labels: list,
		width=620, height=210, max_cats=7) -> str:
	items = list(categories.items())
	if len(items) > max_cats:
		top = items[:max_cats]
		n_periods = len(period_labels)
		other = [sum(items[i][1][j] for i in range(max_cats, len(items)))
			for j in range(n_periods)]
		items = top + [("Other", other)]

	n = len(period_labels)
	totals = [sum(amts[j] for _, amts in items) for j in range(n)]
	vmax = max(totals + [1])

	margin_l, margin_r, margin_t, margin_b = 50, 150, 8, 36
	chart_w = width - margin_l - margin_r
	chart_h = height - margin_t - margin_b
	slot_w = chart_w / n
	bar_w = slot_w * 0.62

	grid = (
		f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l + chart_w}" y2="{margin_t}" '
		f'stroke="#e8e8e8" stroke-width="0.5"/>'
		f'<line x1="{margin_l}" y1="{margin_t + chart_h}" x2="{margin_l + chart_w}" y2="{margin_t + chart_h}" '
		f'stroke="#1a1a1a" stroke-width="0.5"/>'
		f'<text x="{margin_l - 6}" y="{margin_t + 3}" font-size="7" text-anchor="end" fill="#6b7785">{_fmt_compact(vmax)}</text>'
		f'<text x="{margin_l - 6}" y="{margin_t + chart_h + 3}" font-size="7" text-anchor="end" fill="#6b7785">฿0</text>'
	)

	bars = ""
	for j in range(n):
		x0 = margin_l + j * slot_w + (slot_w - bar_w) / 2
		y_cursor = margin_t + chart_h
		for i, (_, amts) in enumerate(items):
			v = max(amts[j], 0)
			h = (v / vmax) * chart_h if vmax > 0 else 0
			if h <= 0:
				continue
			y_cursor -= h
			bars += (
				f'<rect x="{x0:.1f}" y="{y_cursor:.2f}" width="{bar_w:.1f}" height="{h:.2f}" '
				f'fill="{PALETTE[i % len(PALETTE)]}" stroke="#ffffff" stroke-width="0.5"/>'
			)

	xlabels = ""
	for j, lbl in enumerate(period_labels):
		cx = margin_l + j * slot_w + slot_w / 2
		xlabels += (
			f'<text x="{cx:.1f}" y="{margin_t + chart_h + 14}" font-size="7" '
			f'text-anchor="middle" fill="#1a1a1a">{lbl}</text>'
		)

	legend = ""
	for i, (name, _) in enumerate(items):
		ly = margin_t + i * 14
		legend += (
			f'<rect x="{width - margin_r + 8}" y="{ly}" width="9" height="9" '
			f'fill="{PALETTE[i % len(PALETTE)]}"/>'
			f'<text x="{width - margin_r + 22}" y="{ly + 8}" font-size="8" fill="#1a1a1a">{name}</text>'
		)

	return (
		f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
		f'xmlns="http://www.w3.org/2000/svg">{grid}{bars}{xlabels}{legend}</svg>'
	)


def _line_chart_svg(series: dict, period_labels: list,
		width=620, height=210) -> str:
	all_vals = [v for amts in series.values() for v in amts] + [0]
	vmin, vmax = min(all_vals), max(all_vals)
	rng = vmax - vmin or 1
	n = len(period_labels)

	margin_l, margin_r, margin_t, margin_b = 60, 150, 8, 36
	chart_w = width - margin_l - margin_r
	chart_h = height - margin_t - margin_b

	line_palette = {"Cash": "#1a1a1a", "Loan from Investors": "#7d7d7d"}

	def y_at(v):
		return margin_t + chart_h - (v - vmin) / rng * chart_h

	grid = (
		f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l + chart_w}" y2="{margin_t}" '
		f'stroke="#e8e8e8" stroke-width="0.5"/>'
		f'<line x1="{margin_l}" y1="{margin_t + chart_h}" x2="{margin_l + chart_w}" y2="{margin_t + chart_h}" '
		f'stroke="#1a1a1a" stroke-width="0.5"/>'
		f'<text x="{margin_l - 6}" y="{margin_t + 3}" font-size="7" text-anchor="end" fill="#6b7785">{_fmt_compact(vmax)}</text>'
		f'<text x="{margin_l - 6}" y="{margin_t + chart_h + 3}" font-size="7" text-anchor="end" fill="#6b7785">{_fmt_compact(vmin)}</text>'
	)
	if vmin < 0 < vmax:
		zy = y_at(0)
		grid += (
			f'<line x1="{margin_l}" y1="{zy:.1f}" x2="{margin_l + chart_w}" y2="{zy:.1f}" '
			f'stroke="#cccccc" stroke-width="0.5" stroke-dasharray="2,2"/>'
		)

	lines = ""
	for i, (name, amts) in enumerate(series.items()):
		color = line_palette.get(name, PALETTE[i % len(PALETTE)])
		pts = " ".join(
			f"{margin_l + j / max(n - 1, 1) * chart_w:.1f},{y_at(v):.1f}"
			for j, v in enumerate(amts)
		)
		lines += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
		last_x = margin_l + (n - 1) / max(n - 1, 1) * chart_w
		last_y = y_at(amts[-1])
		lines += f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="{color}"/>'

	xlabels = ""
	label_idx = sorted({0, n // 2, n - 1})
	for j in label_idx:
		cx = margin_l + j / max(n - 1, 1) * chart_w
		anchor = "middle" if 0 < j < n - 1 else ("start" if j == 0 else "end")
		xlabels += (
			f'<text x="{cx:.1f}" y="{margin_t + chart_h + 14}" font-size="7" '
			f'text-anchor="{anchor}" fill="#1a1a1a">{period_labels[j]}</text>'
		)

	legend = ""
	for i, name in enumerate(series.keys()):
		ly = margin_t + i * 14
		color = line_palette.get(name, PALETTE[i % len(PALETTE)])
		legend += (
			f'<line x1="{width - margin_r + 8}" y1="{ly + 5}" x2="{width - margin_r + 22}" '
			f'y2="{ly + 5}" stroke="{color}" stroke-width="1.5"/>'
			f'<circle cx="{width - margin_r + 15}" cy="{ly + 5}" r="2" fill="{color}"/>'
			f'<text x="{width - margin_r + 27}" y="{ly + 8}" font-size="8" fill="#1a1a1a">{name}</text>'
		)

	return (
		f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
		f'xmlns="http://www.w3.org/2000/svg">{grid}{lines}{xlabels}{legend}</svg>'
	)


# ─── Page chrome (letterhead, footer, KPI tiles, inception strip) ───────────

# Logo as inline SVG — bulletproof in wkhtmltopdf (no HTTP fetch, no image cache,
# scales to any size). Pulled from /files/logo-black.svg (uploaded by Poom).
LOGO_SVG = '<svg viewBox="0 0 80 24" width="70" height="21" xmlns="http://www.w3.org/2000/svg"><path d="m16.724 23h-3.9539l-6.51834-9.5124-2.06294 1.6761v7.8363h-3.438233v-20.94457h3.438233v10.01387c.42023-.5158.84523-1.0315 1.27501-1.5472.42978-.5158.85956-1.03149 1.28934-1.54723l5.90233-6.91944h3.8823l-7.82197 9.16867zm5.7877-15.85885v15.85885h-3.3666v-15.85885zm-1.6618-6.07421c.5158 0 .9599.13848 1.3323.41545.3821.27697.5731.7545.5731 1.4326 0 .66854-.191 1.14607-.5731 1.43259-.3724.27697-.8165.41546-1.3323.41546-.5348 0-.9885-.13849-1.3609-.41546-.363-.28652-.5444-.76405-.5444-1.43259 0-.6781.1814-1.15563.5444-1.4326.3724-.27697.8261-.41545 1.3609-.41545zm9.8706 21.93306h-3.3809v-22.291214h3.3809zm18.6381-15.85885v15.85885h-2.6503l-.4584-2.1346h-.1863c-.3342.5444-.7592.9981-1.275 1.361-.5157.3534-1.0887.616-1.7191.7879-.6303.1815-1.2941.2722-1.9913.2722-1.1938 0-2.2158-.2005-3.0658-.6017-.8404-.4106-1.4851-1.041-1.934-1.891-.4488-.85-.6733-1.9483-.6733-3.295v-10.35765h3.3809v9.72735c0 1.232.2484 2.1537.745 2.7649.5062.6112 1.2893.9169 2.3495.9169 1.0219 0 1.8337-.2102 2.4354-.6304s1.0267-1.041 1.275-1.8624c.2578-.8213.3868-1.8289.3868-3.0227v-7.89365zm10.7302 13.42345c.4393 0 .8738-.0382 1.3036-.1146.4298-.086.8214-.1863 1.1748-.3009v2.5501c-.3725.1623-.8548.3008-1.447.4154-.5921.1146-1.2081.1719-1.848.1719-.8978 0-1.7048-.148-2.4211-.4441-.7163-.3056-1.2846-.8261-1.7048-1.5615s-.6303-1.7526-.6303-3.0514v-8.524h-2.1633v-1.50423l2.3208-1.18906 1.1031-3.39525h2.1203v3.52419h4.5413v2.56435h-4.5413v8.481c0 .8022.2006 1.3991.6017 1.7907s.9312.5874 1.5902.5874zm9.0683-19.855814v5.601454c0 .58259-.0191 1.15086-.0573 1.70479-.0286.55394-.0621.98372-.1003 1.28934h.1863c.3342-.55394.7449-1.00759 1.232-1.36097.4871-.36292 1.0315-.63512 1.6332-.81658.6112-.18146 1.2606-.27219 1.9483-.27219 1.2129 0 2.2444.20534 3.0944.61602.85.40112 1.4995 1.02669 1.9483 1.8767.4585.85005.6877 1.95315.6877 3.30925v10.3434h-3.3666v-9.713c0-1.232-.2531-2.1537-.7593-2.7649-.5062-.62081-1.2893-.93121-2.3495-.93121-1.0219 0-1.8337.21489-2.4354.64471-.5921.4202-1.0171 1.0458-1.275 1.8767-.2579.8213-.3868 1.8241-.3868 3.0084v7.8793h-3.3666v-22.291214z" fill="#1a1a1a"/></svg>'

LETTER_HEAD = f"""
<table style="width: 100%; text-align: left; font-family: 'Theinhardt', 'IBM Plex Sans Thai', 'Inter', Arial, sans-serif; border-collapse: collapse;">
	<tbody><tr>
		<td style="width: 33%; vertical-align: top; padding: 0;">
			{LOGO_SVG}
		</td>
		<td style="width: 34%; vertical-align: top; font-size: 7pt; color: #D5D5D5; text-align: center; padding: 0; line-height: 1;">
			Confidential
		</td>
		<td style="width: 33%; vertical-align: top; font-size: 7pt; font-weight: 300; text-align: right; padding: 0;">
			hello@kiluth.com<br>
			+66 (0) 65 484 0370<br>
			kiluth.com
		</td>
	</tr></tbody>
</table>
<div style="width: 100%; height: 30px;"></div>
"""

FOOTER = """
<table style="width: 100%; text-align: left; font-family: 'Theinhardt', 'IBM Plex Sans Thai', 'Inter', Arial, sans-serif; border-collapse: collapse;">
	<tbody><tr>
		<td style="width: 50%; vertical-align: top; font-size: 7pt; font-weight: 300; padding: 0;">
			7 Phet Kasem Rd 54 Lane 1<br>
			Bang Duan, Bangkok 10160<br>
			<br>
			01055 68200 199
		</td>
		<td style="width: 50%; vertical-align: top; font-size: 7pt; font-weight: 300; text-align: right; padding: 0;">
			&nbsp;
		</td>
	</tr></tbody>
</table>
"""


def _render_table(headers: list, rows_for_periods: list) -> str:
	period_count = len(headers) - 1
	th_html = "<th></th>" + "".join(
		f"<th style='text-align: right; padding: 8px 12px 8px 8px; font-weight: 600; "
		f"font-size: 9pt; text-transform: uppercase; letter-spacing: 0.5px; "
		f"border-bottom: 1pt solid #1a1a1a;'>{h}</th>"
		for h in headers[1:]
	)

	body_html = ""
	for label, amts, indent, bold in rows_for_periods:
		if not label and not any(amts):
			body_html += "<tr><td colspan='%d' style='height: 8px;'></td></tr>" % (period_count + 1)
			continue
		pad_left = 0 + indent * 14
		weight = "600" if bold else "400"
		border_top = "border-top: 0.5pt solid #1a1a1a;" if bold and label.startswith("Total") else ""
		border_bot = "border-bottom: 1pt solid #1a1a1a;" if bold and label.startswith("Net profit") else ""
		body_html += "<tr>"
		body_html += (
			f"<td style='padding: 4px 0 4px {pad_left}px; font-weight: {weight}; "
			f"font-size: 10pt; {border_top} {border_bot}'>{label}</td>"
		)
		for amt in amts:
			body_html += (
				f"<td style='padding: 4px 12px 4px 8px; text-align: right; "
				f"font-weight: {weight}; font-size: 10pt; "
				f"{border_top} {border_bot}'>{_fmt(amt)}</td>"
			)
		body_html += "</tr>"

	return f"""
	<table style="width: 100%; border-collapse: collapse; margin-top: 18px;">
		<thead><tr>{th_html}</tr></thead>
		<tbody>{body_html}</tbody>
	</table>
	"""


def _render_kpi_tile(label: str, value, prior_value, sparkline_values,
		polarity: str = "up_good") -> str:
	"""polarity: 'up_good' (revenue/cash/net) — green when up; 'up_bad' (expenses) — red when up."""
	delta = (value or 0) - (prior_value or 0)
	if abs(delta) < 0.005:
		delta_str = "—"
		delta_color = "#6b7785"
	else:
		pct = (delta / abs(prior_value) * 100) if prior_value else 0
		sign = "+" if delta > 0 else "−"
		delta_str = f"{sign}{_fmt_compact(abs(delta))} ({pct:+.0f}%)"
		if (delta > 0) == (polarity == "up_good"):
			delta_color = "#1a8a4a"
		else:
			delta_color = "#c4262c"

	spark = _sparkline_svg(sparkline_values, width=140, height=28)

	return f"""
	<td style="border: 0.5pt solid #d5d5d5; padding: 14px 16px; vertical-align: top; width: 50%;">
		<div style="font-size: 8pt; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7785;">{label}</div>
		<div style="font-size: 18pt; font-weight: 700; margin-top: 4px; line-height: 1.1;">{_fmt(value)}</div>
		<div style="font-size: 9pt; color: {delta_color}; margin-top: 4px;">{delta_str} <span style="color: #6b7785;">vs prior month</span></div>
		<div style="margin-top: 8px;">{spark}</div>
	</td>
	"""


def _render_kpi_grid(series: dict) -> str:
	cur = -1
	prv = -2
	rev = series["revenue"]
	exp = series["expenses"]
	net = series["net"]
	cash = series["cash"]

	return f"""
	<table style="width: 100%; border-collapse: separate; border-spacing: 12px 12px; margin-top: 16px;">
		<tr>
			{_render_kpi_tile("Revenue", rev[cur], rev[prv], rev, "up_good")}
			{_render_kpi_tile("Operating expenses", exp[cur], exp[prv], exp, "up_bad")}
		</tr>
		<tr>
			{_render_kpi_tile("Net profit / (loss)", net[cur], net[prv], net, "up_good")}
			{_render_kpi_tile("Cash on hand", cash[cur], cash[prv], cash, "up_good")}
		</tr>
	</table>
	"""


def _render_inception_strip(period_end) -> str:
	earliest = datetime.date(2000, 1, 1)
	total_revenue = -_sum_root("Income", earliest, period_end)
	total_expenses = _sum_root("Expense", earliest, period_end)
	net = total_revenue - total_expenses
	loan_outstanding = _loan_balance_on(period_end)

	cells = [
		("Lifetime revenue", total_revenue),
		("Lifetime expenses", total_expenses),
		("Lifetime net", net),
		("Loan outstanding", loan_outstanding),
	]
	# Drop left border on first cell.
	cell_html = ""
	for i, (label, v) in enumerate(cells):
		border = "" if i == 0 else "border-left: 0.5pt solid #d5d5d5;"
		cell_html += (
			f'<td style="padding: 10px 14px; {border} vertical-align: top;">'
			f'<div style="font-size: 7pt; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7785;">{label}</div>'
			f'<div style="font-size: 12pt; font-weight: 700; margin-top: 2px;">{_fmt(v)}</div>'
			f'</td>'
		)
	return f"""
	<div style="margin-top: 22px;">
		<div style="font-size: 8pt; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7785; margin-bottom: 6px;">
			Since inception
		</div>
		<table style="width: 100%; border-collapse: collapse; border-top: 0.5pt solid #1a1a1a; border-bottom: 0.5pt solid #1a1a1a;">
			<tr>{cell_html}</tr>
		</table>
	</div>
	"""


# ─── Fonts (served by Frappe at /files/, accessed via absolute URL) ─────────
# wkhtmltopdf is flaky with base64 data: URLs in @font-face. Serving the TTFs
# from Frappe's File doctype (uploaded once via /desk/file) gives wkhtmltopdf
# a same-origin HTTP URL it can fetch reliably. Files are public so no auth.


def _font_face_block() -> str:
	from frappe.utils import get_url

	mapping = [
		("theinhardt-light-webfont.ttf", 300, "normal"),
		("theinhardt-lightita-webfont.ttf", 300, "italic"),
		("theinhardt-regular-webfont.ttf", 400, "normal"),
		("theinhardt-regularita-webfont.ttf", 400, "italic"),
		("theinhardt-bold-webfont.ttf", 700, "normal"),
		("theinhardt-boldita-webfont.ttf", 700, "italic"),
	]
	out = []
	for fname, weight, style in mapping:
		url = get_url(f"/files/{fname}")
		out.append(
			f"@font-face {{ font-family: 'Theinhardt'; "
			f"src: url('{url}') format('truetype'); "
			f"font-weight: {weight}; font-style: {style}; }}"
		)
	return "\n".join(out)


# ─── HTML assembly ──────────────────────────────────────────────────────────

def _render_html(period: dict) -> str:
	period_start = period["start"]
	period_end = period["end"]
	prior_start = period["prior_month_start"]
	prior_end = period["prior_month_end"]
	fy_start = period["fy_start"]
	ttm_start = period["ttm_start"]

	series = _build_monthly_series(period_end, n=12)

	pl_rows = _build_pl_table([
		(period_start, period_end),
		(prior_start, prior_end),
		(fy_start, period_end),
		(ttm_start, period_end),
	])
	bs_rows = _build_bs_table([period_end, prior_end])

	pl_table = _render_table(
		["", period_start.strftime("%B %Y"), prior_start.strftime("%B %Y"),
			"Year to date", "Last 12 mo"],
		pl_rows,
	)
	bs_table = _render_table(
		["", period_end.strftime("%d %b %Y"), prior_end.strftime("%d %b %Y")],
		bs_rows,
	)

	expense_chart = _stacked_bar_svg(series["expense_by_cat"], series["labels"])
	cash_loan_chart = _line_chart_svg(
		{"Cash": series["cash"], "Loan from Investors": series["loan"]},
		series["labels"],
	)
	kpi_grid = _render_kpi_grid(series)
	inception = _render_inception_strip(period_end)

	page_style = (
		_font_face_block()
		+ """
		@page { size: A4; margin: 16mm 14mm 22mm 14mm; }
		body { font-family: 'Theinhardt', 'IBM Plex Sans Thai', 'Inter', Arial, sans-serif; color: #1a1a1a; font-size: 10pt; line-height: 1.45; margin: 0; padding: 0; }
		h1 { font-size: 22pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin: 12pt 0 4pt 0; }
		.sub { font-size: 9pt; font-weight: 400; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7785; }
		/* Pages flow naturally; explicit break BEFORE each page (except first) avoids
		   the wkhtmltopdf "absolute footer overflow → blank page" trap. Footer is the
		   last block in each page so it sits below content rather than glued to the
		   page bottom — a tradeoff we accept to guarantee no spurious pages. */
		.page { page-break-before: always; }
		.page:first-child { page-break-before: auto; }
		.page-footer { margin-top: 28px; padding-top: 10px; border-top: 0.5pt solid #e8e8e8; }
		"""
	)

	chart_caption = (
		'<div style="font-size: 8pt; text-transform: uppercase; letter-spacing: 0.5px; '
		'color: #6b7785; margin-top: 18px; margin-bottom: 4px;">'
	)

	page1 = f"""
	<div class="page">
		{LETTER_HEAD}
		<h1>Monthly Report</h1>
		<div class="sub">{period_end.strftime("%B %Y")} · Kiluth LTD.</div>
		{kpi_grid}
		{inception}
		<div class="page-footer">{FOOTER}</div>
	</div>
	"""
	page2 = f"""
	<div class="page">
		{LETTER_HEAD}
		<h1>Statement of Operations</h1>
		<div class="sub">For the month ended {period_end.strftime("%d %B %Y")}</div>
		{pl_table}
		{chart_caption}Operating expenses by category — last 12 months</div>
		{expense_chart}
		<div class="page-footer">{FOOTER}</div>
	</div>
	"""
	page3 = f"""
	<div class="page">
		{LETTER_HEAD}
		<h1>Balance Sheet</h1>
		<div class="sub">As at {period_end.strftime("%d %B %Y")}</div>
		{bs_table}
		{chart_caption}Cash and loan position — last 12 months</div>
		{cash_loan_chart}
		<div class="page-footer">{FOOTER}</div>
	</div>
	"""

	return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{page_style}</style></head>
<body>{page1}{page2}{page3}</body></html>
"""


def _email_body(period: dict) -> str:
	# Greetings only — all financial detail lives in the attached PDF.
	start_str = period["start"].strftime("%-d")
	end_str = period["end"].strftime("%-d %B %Y")
	return (
		f"<p>Hi team,</p>"
		f"<p>Kiluth's financial report for <strong>{start_str}–{end_str}</strong> is attached.</p>"
		f"<p>— Kiluth Portal</p>"
	)
