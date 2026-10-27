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

The PDF design (black pages, photo cover) lives in utils/report_pdf.py,
shared with the Close Report and the Learning reports.
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import getdate, nowdate


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

# ─── Idempotency state ──────────────────────────────────────────────────────
# We record "the last period we sent the production report for" via Frappe's
# Defaults table — a key/value store that survives restarts. The value is the
# period label ("YYYY-MM") of the prior-month being reported.

_SENT_KEY = "kiluth_monthly_report_last_sent_period"


def _last_sent_period() -> str | None:
	return frappe.db.get_default(_SENT_KEY)


def _mark_sent(period_key: str) -> None:
	frappe.db.set_default(_SENT_KEY, period_key)


# ─── Public entry point ─────────────────────────────────────────────────────

@frappe.whitelist()
def send_monthly_report(recipients: list[str] | str | None = None):
	"""Build and email the prior month's financial report.

	`recipients` defaults to the module-level RECIPIENTS tuple (the cron uses
	this). Manual invocations can pass a single email or a list to override —
	handy for testing without spamming the management group. Only users with
	the System Manager role can call this via the API.

	Idempotency: when called via the production path (no `recipients` arg),
	skips if the current period's report has already been sent. Test calls
	with an explicit `recipients` list always send (so the test send is
	always observable and never accidentally suppressed).
	"""
	if not frappe.has_permission("Server Script", "write"):
		# Reuse Server Script perm as a proxy for "trusted enough to email
		# financial data" — System Manager has it by default.
		frappe.throw("Not permitted to send the monthly financial report.")

	is_test_send = recipients is not None

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
	period_key = period["start"].strftime("%Y-%m")

	# Idempotency guard — production path only. Test sends always go through
	# so a manual fire never gets silently swallowed.
	if not is_test_send and _last_sent_period() == period_key:
		return {"period": period["label"], "skipped": "already sent"}

	from kiluth_portal.utils.report_pdf import pdf

	pdf_bytes = pdf(_render_html(period))

	subject = f"Kiluth — Monthly Financial Report — {period['label']}"
	fname = f"Kiluth-Financial-Report-{period['start'].strftime('%Y-%m')}.pdf"
	body = _email_body(period, fname)
	attachment = {
		"fname": fname,
		"fcontent": pdf_bytes,
	}

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=body,
		attachments=[attachment],
		delayed=False,
	)

	if not is_test_send:
		_mark_sent(period_key)

	return {"period": period["label"], "recipients": recipients}


def send_monthly_report_catchup():
	"""Hourly catch-up — sends the report if today is past the scheduled
	5th-09:00 fire and the current period hasn't been delivered yet.

	The cron `0 9 5 * *` fires once at 09:00 on the 5th. If the server is
	down or restarting at that minute, the cron is missed and Frappe does
	not catch up. This function runs hourly and re-attempts; the idempotency
	guard in send_monthly_report ensures a single email per period.

	No-op if the period for "today" hasn't passed its scheduled fire time.
	"""
	today = getdate(nowdate())
	period = _compute_period()
	period_key = period["start"].strftime("%Y-%m")

	# Already sent for this period — done.
	if _last_sent_period() == period_key:
		return

	# We only fire on/after the 5th of any given month at 09:00.
	now_dt = frappe.utils.now_datetime()
	if today.day < 5 or (today.day == 5 and now_dt.hour < 9):
		return

	send_monthly_report()  # uses production recipients; idempotency-protected


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


# ─── Charts (SVG in mm, white on black) ──────────────────────────────────────
# Design: kiluth_portal/utils/report_pdf.py (design A, 2026-10-27). Categories
# are told apart by shades of grey; mint is kept for the one accent.

GREYS = ("#e8e8e8", "#b0b0b0", "#808080", "#5a5a5a", "#404040", "#2e2e2e", "#d0d0d0", "#6e6e6e")


def _legend(names, colors) -> str:
	return "<div class='legend'>" + "".join(
		f"<span><span style='color:{c}'>&#9632;</span>&nbsp;{n}</span>" for n, c in zip(names, colors)) + "</div>"


def _bars_svg(categories: dict, labels: list, w=174, h=62, max_cats=7) -> str:
	items = list(categories.items())
	if len(items) > max_cats:
		other = [sum(items[i][1][j] for i in range(max_cats, len(items))) for j in range(len(labels))]
		items = items[:max_cats] + [("Other", other)]
	n = len(labels)
	top = max([sum(max(a[j], 0) for _, a in items) for j in range(n)] + [1])
	bw = w / n * 0.5
	out = (f"<text x='0' y='3' font-size='2.4' fill='#5a5a5a'>{_fmt_compact(top)}</text>"
		f"<line x1='0' x2='{w}' y1='{h - 6}' y2='{h - 6}' stroke='#3a3a3a' stroke-width='0.3'/>")
	for j in range(n):
		x = j * w / n + (w / n - bw) / 2
		y = h - 6
		for k, (_, amts) in enumerate(items):
			bh = max(amts[j], 0) / top * (h - 12)
			if bh <= 0:
				continue
			y -= bh
			out += f"<rect x='{x:.1f}' y='{y:.2f}' width='{bw:.1f}' height='{bh:.2f}' fill='{GREYS[k % len(GREYS)]}'/>"
		out += f"<text x='{x + bw / 2:.1f}' y='{h - 1}' font-size='2.6' fill='#7a7a7a' text-anchor='middle'>{labels[j]}</text>"
	svg = f"<svg width='{w}mm' height='{h}mm' viewBox='0 0 {w} {h}' style='margin-top:4mm' xmlns='http://www.w3.org/2000/svg'>{out}</svg>"
	return svg + _legend([nm for nm, _ in items], GREYS)


def _lines_svg(series: dict, labels: list, w=174, h=56) -> str:
	colors = ("#ffffff", "#7a7a7a")
	vals = [v for a in series.values() for v in a] + [0]
	lo, hi = min(vals), max(vals) * 1.1 or 1
	span = (hi - lo) or 1
	n = len(labels)
	y_at = lambda v: 4 + (1 - (v - lo) / span) * (h - 14)
	out = ""
	for g in range(5):
		v = hi - g * span / 4
		y = y_at(v)
		out += (f"<line x1='0' x2='{w}' y1='{y:.1f}' y2='{y:.1f}' stroke='#1f1f1f' stroke-width='0.3'/>"
			f"<text x='0' y='{y - 1:.1f}' font-size='2.4' fill='#5a5a5a'>{_fmt_compact(v)}</text>")
	for k, amts in enumerate(series.values()):
		pts = " ".join(f"{j * w / max(n - 1, 1):.1f},{y_at(v):.1f}" for j, v in enumerate(amts))
		out += f"<polyline points='{pts}' fill='none' stroke='{colors[k % 2]}' stroke-width='0.6'/>"
	for j, lbl in enumerate(labels):
		anchor = "start" if j == 0 else ("end" if j == n - 1 else "middle")
		out += f"<text x='{j * w / max(n - 1, 1):.1f}' y='{h - 1}' font-size='2.6' fill='#7a7a7a' text-anchor='{anchor}'>{lbl}</text>"
	svg = f"<svg width='{w}mm' height='{h}mm' viewBox='0 0 {w} {h}' style='margin-top:4mm' xmlns='http://www.w3.org/2000/svg'>{out}</svg>"
	return svg + _legend(list(series), colors)


# ─── Cover: KPI tiles and the since-inception strip ─────────────────────────

def _kpi_tile(label: str, values: list, prior_label: str, up_good=True) -> str:
	from kiluth_portal.utils.report_pdf import sparkline

	cur, prv = values[-1], values[-2]
	d = cur - prv
	if abs(d) < 0.005:
		delta = "<span class='muted'>No change</span>"
	else:
		pct = f" ({d / abs(prv) * 100:+.0f}%)" if prv else ""
		cls = "good" if (d > 0) == up_good else "bad"
		delta = f"<span class='{cls}'>{'+' if d > 0 else '−'}{abs(d):,.0f}{pct}</span>"
	return (f"<td><div class='k'>{label}</div><div class='v'>{_fmt(cur)}</div>"
		f"<div class='d'>{delta} <span class='muted'>vs {prior_label}</span></div>{sparkline(values)}</td>")


def _kpi_grid(series: dict, prior_label: str) -> str:
	t = lambda *a: _kpi_tile(*a[:2], prior_label, *a[2:])
	return (f"<table class='kpi'><tr>{t('Revenue', series['revenue'])}{t('Operating expenses', series['expenses'], False)}</tr>"
		f"<tr>{t('Net profit / (loss)', series['net'])}{t('Cash on hand', series['cash'])}</tr></table>")


def _inception_strip(period_end) -> str:
	from kiluth_portal.utils.report_pdf import heading

	earliest = datetime.date(2000, 1, 1)
	revenue = -_sum_root("Income", earliest, period_end)
	expenses = _sum_root("Expense", earliest, period_end)
	cells = [("Revenue", revenue), ("Expenses", expenses), ("Net", revenue - expenses),
		("Loan outstanding", _loan_balance_on(period_end))]
	return heading("Since inception") + "<table class='strip'><tr>" + "".join(
		f"<td><div class='k'>{k}</div>{_fmt(v)}</td>" for k, v in cells) + "</tr></table>"


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

def _statement_rows(rows: list) -> list:
	"""(label, amts, indent, bold) rows → report_pdf table rows."""
	out = []
	for label, amts, indent, bold in rows:
		if not label:
			continue
		if all(a is None for a in amts):
			out.append(([label] + [""] * len(amts), "sec"))
			continue
		kind = "total" if bold else ("ind" if indent else "")
		out.append(([label] + [_fmt(a) for a in amts], kind))
	return out


def _render_html(period: dict) -> str:
	from kiluth_portal.utils import report_pdf as rp

	period_start, period_end = period["start"], period["end"]
	prior_start, prior_end = period["prior_month_start"], period["prior_month_end"]
	series = _build_monthly_series(period_end, n=12)
	month = period_end.strftime("%B %Y")

	pl_rows = _build_pl_table([
		(period_start, period_end),
		(prior_start, prior_end),
		(period["fy_start"], period_end),
		(period["ttm_start"], period_end),
	])
	bs_rows = _build_bs_table([period_end, prior_end])

	cover = rp.cover(rp.photo("email/hero-financial.jpg"), "Monthly report", month,
		"Kiluth's money: the month, the year, and where it stands.")
	blocks = [
		rp.Block(_kpi_grid(series, prior_start.strftime("%B")) + _inception_strip(period_end), 120),
		rp.NewPage("Statement of operations", f"For the month ended {period_end.strftime('%d %B %Y')}"),
		rp.Table("Profit and loss", ["", period_start.strftime("%b %Y"), prior_start.strftime("%b %Y"),
			"Year to date", "Last 12 mo"], _statement_rows(pl_rows), right=(1, 2, 3, 4)),
		rp.Block(rp.heading("Operating expenses by category, last 12 months")
			+ _bars_svg(series["expense_by_cat"], series["labels"]), 92),
		rp.NewPage("Balance sheet", f"As at {period_end.strftime('%d %B %Y')}"),
		rp.Table("Assets, liabilities and equity", ["", period_end.strftime("%d %b %Y"), prior_end.strftime("%d %b %Y")],
			_statement_rows(bs_rows), widths=[46, 27, 27], right=(1, 2)),
		rp.Block(rp.heading("Cash and loan, last 12 months")
			+ _lines_svg({"Cash": series["cash"], "Loan from investors": series["loan"]}, series["labels"]), 84),
	]
	pages = rp.paginate(blocks, rp.CONTENT_END - rp.COVER_BODY_TOP, "Monthly report", month)
	return rp.document(f"Kiluth Monthly Report {month}", cover, pages)


def _email_body(period: dict, fname: str = "") -> str:
	# Greetings only — all financial detail lives in the attached PDF.
	# Look: kiluth_portal/utils/report_email.py (the Portal email design, 2026-10-27).
	from frappe.utils import get_url

	from kiluth_portal.utils.report_email import email_html

	return email_html(
		title="Monthly Financial Report",
		kicker=period["label"],
		lines=["Hi team,", f"Kiluth's financial report for **{_period_range(period)}** is attached."],
		hero="hero-financial.jpg",
		assets=get_url("/assets/kiluth_portal/"),
		portal_url=get_url(),
		attachment=fname,
	)


def _period_range(period: dict) -> str:
	"""1–30 September 2026"""
	return f"{period['start'].strftime('%-d')}–{period['end'].strftime('%-d %B %Y')}"
