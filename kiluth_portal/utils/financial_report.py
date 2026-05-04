"""Monthly financial report — auto-emailed PDF.

Runs on the 5th of every month at 09:00 (Asia/Bangkok). Builds a one-page
PDF covering the prior full month + YTD, and emails it to a fixed list of
recipients. The cron schedule lives in `hooks.py` under `scheduler_events`.

Why this exists in code (not as a Server Script):
- Server Scripts need `server_script_enabled` flag in site_config.json
  which we deliberately leave off (security default).
- Code in the app is version-controlled and survives redeploys.

Privacy: the underlying loan account is named after a real investor.
For the PDF we relabel it to "Loan from Investors" (NAME_REMAP). All other
account names render as-is minus the company suffix " - K".

Manual test: it's safe (and whitelisted) to invoke directly; pass an
explicit recipients list to avoid emailing the full distribution while
sanity-checking output. From the browser console:

    await frappe.call({
        method: 'kiluth_portal.utils.financial_report.send_monthly_report',
        args: {recipients: ['poom.pengcharoen@kiluth.com']}
    })

Idempotency: each invocation builds a fresh report covering the prior
calendar month relative to "now", so re-runs on the same day produce the
same content. Multiple invocations the same day = duplicate emails (the
scheduler won't double-fire, but `bench execute` for testing might).
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import getdate, nowdate
from frappe.utils.pdf import get_pdf


COMPANY = "Kiluth"
CURRENCY = "฿"
RECIPIENTS = (
	"poom.pengcharoen@kiluth.com",
	"phuttipan.samranruen@kiluth.com",
)

# Per-account relabeling for privacy. The full ERPNext account name (with
# the " - K" company suffix) maps to the label that appears in the PDF.
NAME_REMAP = {
	"Loan from Pavaruth Pengcharoen - K": "Loan from Investors",
}


# ─── Public entry point ─────────────────────────────────────────────────────

@frappe.whitelist()
def send_monthly_report(recipients: list[str] | str | None = None):
	"""Build and email the prior month's financial report.

	`recipients` defaults to the module-level RECIPIENTS tuple (the cron
	uses this). Manual invocations can pass a single email or a list to
	override — handy for testing without spamming everyone. Only users
	with the System Manager role can call this via the API.
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
	data = _pull_data(period)
	html = _render_html(period, data)
	pdf_bytes = get_pdf(html)

	subject = f"Kiluth — Monthly Financial Report — {period['label']}"
	body = _email_body(period, data)
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


# ─── Period helpers ─────────────────────────────────────────────────────────

def _compute_period() -> dict:
	"""Prior full month relative to today."""
	today_dt = getdate(nowdate())
	first_of_this = today_dt.replace(day=1)
	last_of_prior = first_of_this - datetime.timedelta(days=1)
	period_start = last_of_prior.replace(day=1)
	period_end = last_of_prior

	return {
		"start": period_start,
		"end": period_end,
		"label": period_start.strftime("%B %Y"),
		"fy_start": period_start.replace(month=1, day=1),
		"prior_month_end": period_start - datetime.timedelta(days=1),
	}


# ─── Data pull ──────────────────────────────────────────────────────────────

def _pull_data(period: dict) -> dict:
	period_start = period["start"]
	period_end = period["end"]
	fy_start = period["fy_start"]
	prior_month_end = period["prior_month_end"]

	income_month = -_sum_root("Income", period_start, period_end)
	expense_month = _sum_root("Expense", period_start, period_end)
	profit_month = income_month - expense_month

	income_ytd = -_sum_root("Income", fy_start, period_end)
	expense_ytd = _sum_root("Expense", fy_start, period_end)
	profit_ytd = income_ytd - expense_ytd

	assets = _root_balance_at("Asset", period_end)
	liabilities = -_root_balance_at("Liability", period_end)
	equity = -_root_balance_at("Equity", period_end)

	cash_now = _account_balance_on("Cash - K", period_end)
	loan_account = "Loan from Pavaruth Pengcharoen - K"
	loan_now = -_account_balance_on(loan_account, period_end)
	loan_prior_end = -_account_balance_on(loan_account, prior_month_end)

	income_lines = _income_breakdown(period_start, period_end)
	expense_lines = _expense_breakdown(period_start, period_end, top_n=8)

	cogs_month = sum(r["amt"] for r in expense_lines if r["name"] == "Cost of Goods Sold - K")
	gross_margin = ((income_month - cogs_month) / income_month * 100) if income_month > 0 else None

	return {
		"income_month": income_month,
		"expense_month": expense_month,
		"profit_month": profit_month,
		"income_ytd": income_ytd,
		"expense_ytd": expense_ytd,
		"profit_ytd": profit_ytd,
		"assets": assets,
		"liabilities": liabilities,
		"equity": equity,
		"cash_now": cash_now,
		"loan_now": loan_now,
		"loan_prior_end": loan_prior_end,
		"loan_change": loan_now - loan_prior_end,
		"income_lines": income_lines,
		"expense_lines": expense_lines,
		"cogs_month": cogs_month,
		"gross_margin": gross_margin,
	}


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


def _root_balance_at(root_type: str, on_date) -> float:
	res = frappe.db.sql(
		"""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0
			AND acc.root_type = %s
			AND gle.posting_date <= %s
		""",
		(COMPANY, root_type, on_date),
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


def _income_breakdown(start, end) -> list[dict]:
	rows = frappe.db.sql(
		"""
		SELECT acc.name, -SUM(gle.debit - gle.credit) AS amt
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0
			AND acc.root_type = 'Income'
			AND gle.posting_date BETWEEN %s AND %s
		GROUP BY acc.name
		HAVING ABS(amt) > 0.005
		ORDER BY amt DESC
		""",
		(COMPANY, start, end),
		as_dict=True,
	)
	return rows


def _expense_breakdown(start, end, top_n: int = 8) -> list[dict]:
	rows = frappe.db.sql(
		"""
		SELECT acc.name, SUM(gle.debit - gle.credit) AS amt
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0
			AND acc.root_type = 'Expense'
			AND gle.posting_date BETWEEN %s AND %s
		GROUP BY acc.name
		HAVING ABS(amt) > 0.005
		ORDER BY amt DESC
		""",
		(COMPANY, start, end),
		as_dict=True,
	)
	return rows[:top_n]


# ─── Rendering ──────────────────────────────────────────────────────────────

def _relabel(account: str) -> str:
	return NAME_REMAP.get(account, account.replace(" - K", "").strip())


def _fmt(amount) -> str:
	if amount is None:
		return "—"
	if abs(amount) < 0.005:
		return f"{CURRENCY} 0.00"
	return f"{CURRENCY} {amount:,.2f}"


def _row(label: str, amount, *, bold: bool = False, indent: int = 0, color: str | None = None) -> str:
	style = []
	if bold:
		style.append("font-weight: 600")
	if color:
		style.append(f"color: {color}")
	pad_left = 20 + indent * 16
	style_left = ";".join(style + [f"padding-left: {pad_left}px"])
	style_right = ";".join(style + ["text-align: right; padding-right: 20px"])
	return f"<tr><td style='{style_left}'>{label}</td><td style='{style_right}'>{_fmt(amount)}</td></tr>"


def _section_title(label: str) -> str:
	return (
		"<tr><td colspan='2' style='background:#f4f6fa;padding:10px 20px;"
		"font-weight:600;font-size:13px;letter-spacing:.5px;text-transform:uppercase;"
		f"color:#3c4858'>{label}</td></tr>"
	)


def _render_html(period: dict, d: dict) -> str:
	loss_color = "#c0392b" if d["profit_month"] < 0 else "#27ae60"
	ytd_loss_color = "#c0392b" if d["profit_ytd"] < 0 else "#27ae60"
	loan_change_color = "#c0392b" if d["loan_change"] > 0 else "#27ae60"

	income_rows = "".join(
		_row(_relabel(r["name"]), r["amt"], indent=1) for r in d["income_lines"]
	)
	expense_rows = "".join(
		_row(_relabel(r["name"]), r["amt"], indent=1) for r in d["expense_lines"]
	)

	return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'>
<style>
	@page {{ size: A4; margin: 18mm 14mm }}
	body  {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #2c3e50; font-size: 11px; line-height: 1.45 }}
	h1    {{ font-size: 20px; margin: 0; color: #1a2332 }}
	h2    {{ font-size: 13px; text-transform: uppercase; letter-spacing: .5px; color: #3c4858; border-bottom: 1px solid #dfe4ea; padding-bottom: 4px; margin-top: 26px }}
	table {{ width: 100%; border-collapse: collapse; margin-top: 6px }}
	td    {{ padding: 6px 0 }}
	.head {{ background: #1a2332; color: #fff; padding: 22px 24px; border-radius: 4px }}
	.head .sub {{ opacity: .8; font-size: 12px; margin-top: 4px }}
	.kpi  {{ display: inline-block; width: 30%; padding: 14px; margin-right: 1.5%; background: #f7f9fb; border-radius: 4px; vertical-align: top }}
	.kpi .lbl {{ font-size: 10px; text-transform: uppercase; color: #6b7785; letter-spacing: .5px }}
	.kpi .val {{ font-size: 16px; font-weight: 600; margin-top: 4px }}
	.kpi .delta {{ font-size: 10px; margin-top: 4px }}
	.footer {{ margin-top: 30px; padding-top: 14px; border-top: 1px solid #dfe4ea; font-size: 9px; color: #8a96a3; text-align: center }}
</style>
</head>
<body>

<div class='head'>
	<h1>Kiluth — Monthly Financial Report</h1>
	<div class='sub'>{period['label']}  ·  Generated {nowdate()}</div>
</div>

<div style='margin-top: 22px'>
	<div class='kpi'>
		<div class='lbl'>Net Result · Month</div>
		<div class='val' style='color:{loss_color}'>{_fmt(d['profit_month'])}</div>
	</div>
	<div class='kpi'>
		<div class='lbl'>Net Result · YTD</div>
		<div class='val' style='color:{ytd_loss_color}'>{_fmt(d['profit_ytd'])}</div>
	</div>
	<div class='kpi'>
		<div class='lbl'>Loan from Investors</div>
		<div class='val'>{_fmt(d['loan_now'])}</div>
		<div class='delta' style='color:{loan_change_color}'>Δ {_fmt(d['loan_change'])} this month</div>
	</div>
</div>

<h2>Profit &amp; Loss — {period['label']}</h2>
<table>
	{_section_title("Income")}
	{income_rows}
	{_row("Total Income", d['income_month'], bold=True)}
	{_section_title("Expenses")}
	{expense_rows}
	{_row("Total Expenses", d['expense_month'], bold=True)}
	<tr><td colspan='2' style='border-top:1px solid #dfe4ea'></td></tr>
	{_row("Net Profit / (Loss)", d['profit_month'], bold=True, color=loss_color)}
</table>

<h2>Profit &amp; Loss — Year to Date</h2>
<table>
	{_row("Total Income", d['income_ytd'])}
	{_row("Total Expenses", d['expense_ytd'])}
	{_row("Net Profit / (Loss)", d['profit_ytd'], bold=True, color=ytd_loss_color)}
</table>

<h2>Balance Sheet — As of {period['end'].strftime('%d %B %Y')}</h2>
<table>
	{_row("Total Assets", d['assets'])}
	{_row("Total Liabilities", d['liabilities'])}
	{_row("Total Equity", d['equity'])}
	<tr><td colspan='2' style='border-top:1px solid #dfe4ea'></td></tr>
	{_row("Loan from Investors", d['loan_now'], bold=True)}
	{_row("Cash on Hand", d['cash_now'], bold=True)}
</table>

<div class='footer'>
	Kiluth LTD. — confidential. Auto-generated from ERPNext on {nowdate()}.
</div>

</body>
</html>
"""


def _email_body(period: dict, d: dict) -> str:
	return (
		f"<p>Hi team,</p>"
		f"<p>Attached is Kiluth's financial report for <strong>{period['label']}</strong>.</p>"
		f"<ul>"
		f"<li>Net result this month: <strong>{_fmt(d['profit_month'])}</strong></li>"
		f"<li>Net result year-to-date: <strong>{_fmt(d['profit_ytd'])}</strong></li>"
		f"<li>Loan from Investors: <strong>{_fmt(d['loan_now'])}</strong> "
		f"(Δ {_fmt(d['loan_change'])} this month)</li>"
		f"</ul>"
		f"<p>The PDF has the full P&amp;L and Balance Sheet detail.</p>"
		f"<p>— Kiluth automated reporting</p>"
	)
