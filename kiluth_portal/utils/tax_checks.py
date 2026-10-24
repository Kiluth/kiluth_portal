"""Two Thai tax checks the Portal runs for itself.

Kiluth files no tax returns today and nobody was measuring either of these.
Both checks raise a Task and otherwise stay silent, so a quiet month costs
nothing and a problem is impossible to miss.

1. **Withholding.** When Kiluth pays a Thai person or company ฿1,000 or more
   for a service it must withhold 3%, issue a 50 ทวิ, and file ภ.ง.ด.3 (person)
   or ภ.ง.ด.53 (company) by the 7th of the next month. Across 2025-26 that was
   19 payments and ฿8,598.22 of tax, none of it withheld. Runs on the 3rd, four
   days before the deadline.

2. **VAT threshold.** Registration is required within 30 days of income passing
   ฿1.8 million in a year. Runs weekly and says nothing until income reaches
   75% of the line.

Which suppliers attract withholding cannot be read from the data: every
supplier on this site is `country = Thailand`, including Google and AWS, and
`supplier_group` is almost entirely "Local". So it is a decision recorded on
the Supplier itself — `custom_withhold_3pct`, with `custom_withholding_reviewed`
marking that a human has looked. An unreviewed supplier is reported, never
assumed either way.

Rules: docs.kiluth.com/finance/tax
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, add_to_date, flt, get_first_day, get_last_day, getdate, nowdate

PROJECT = "PROJ-0001"
DEPARTMENT = "Finance - K"
OWNER_KEY = "kiluth_tax_task_owner"
DEFAULT_OWNER = "poom.pengcharoen@kiluth.com"
DOC_URL = "https://docs.kiluth.com/finance/tax"

WHT_ACCOUNT = "Withholding Tax Payable - K"
INCOME_ACCOUNT = "Sales - K"
WHT_MINIMUM = 1000.0
WHT_RATE = 0.03
VAT_LINE = 1_800_000.0
VAT_WARN_AT = 0.75


def _owner() -> str:
	return frappe.db.get_default(OWNER_KEY) or DEFAULT_OWNER


def _raise_task(subject: str, description: str, priority: str = "Medium") -> str | None:
	"""Create and assign one task. Returns None if that subject already exists."""
	if frappe.db.exists("Task", {"subject": subject, "status": ["not in", ["Completed", "Cancelled"]]}):
		return None
	task = frappe.get_doc({
		"doctype": "Task",
		"subject": subject,
		"project": PROJECT,
		"department": DEPARTMENT,
		"status": "Open",
		"priority": priority,
		"description": description,
	}).insert(ignore_permissions=True)
	from frappe.desk.form.assign_to import add as assign

	assign({"doctype": "Task", "name": task.name, "assign_to": [_owner()]})
	frappe.db.commit()
	return task.name


# ---------------------------------------------------------------- withholding


def _vouchers_with_withholding(start, end) -> set[str]:
	rows = frappe.get_all(
		"GL Entry",
		filters={
			"account": WHT_ACCOUNT,
			"is_cancelled": 0,
			"posting_date": ["between", [start, end]],
		},
		fields=["voucher_no"],
	)
	return {r.voucher_no for r in rows}


def _withholding_candidates(start, end):
	"""Service payments in the window with no 3% recorded, split by whether a human has classified the supplier."""
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"posting_date": ["between", [start, end]],
			"grand_total": [">=", WHT_MINIMUM],
		},
		fields=["name", "posting_date", "supplier", "grand_total"],
		order_by="posting_date asc",
	)
	if not invoices:
		return [], []

	already = _vouchers_with_withholding(start, end)
	suppliers = {i.supplier for i in invoices}
	flags = {
		s.name: (s.custom_withhold_3pct, s.custom_withholding_reviewed)
		for s in frappe.get_all(
			"Supplier",
			filters={"name": ["in", list(suppliers)]},
			fields=["name", "custom_withhold_3pct", "custom_withholding_reviewed"],
		)
	}

	due, unclassified = [], []
	for inv in invoices:
		if inv.name in already:
			continue
		withhold, reviewed = flags.get(inv.supplier, (0, 0))
		if not reviewed:
			unclassified.append(inv)
		elif withhold:
			due.append(inv)
	return due, unclassified


def _withholding_description(label, due, unclassified) -> str:
	parts = [
		f"The Portal found service payments in {label} with no 3% withholding recorded. "
		f"Rule: <a href=\"{DOC_URL}\">Tax</a>. ภ.ง.ด.3 (person) or ภ.ง.ด.53 (company) "
		f"is due by the 7th.<br><br>"
	]
	if due:
		total = sum(flt(i.grand_total) for i in due)
		parts.append(
			f"<b>Withholding due — {len(due)} payment(s), ฿{total:,.2f}, 3% = ฿{total * WHT_RATE:,.2f}</b><br>"
		)
		parts.append("<ul>")
		for i in due:
			parts.append(
				f"<li>{i.posting_date} — {i.supplier} — ฿{flt(i.grand_total):,.2f} "
				f"(3% = ฿{flt(i.grand_total) * WHT_RATE:,.2f}) — {i.name}</li>"
			)
		parts.append("</ul>")
	if unclassified:
		parts.append(
			f"<br><b>Supplier not classified — {len(unclassified)} payment(s)</b><br>"
			f"Nobody has said whether these suppliers attract Thai withholding. Decide on each "
			f"Supplier record (Withhold 3%, then tick Withholding Reviewed) so the next run is clean. "
			f"Country and supplier group cannot answer this — every supplier here is tagged Thailand.<br>"
		)
		parts.append("<ul>")
		for i in unclassified:
			parts.append(f"<li>{i.posting_date} — {i.supplier} — ฿{flt(i.grand_total):,.2f} — {i.name}</li>")
		parts.append("</ul>")
	parts.append(
		"<br><b>Done when</b> each payment above is either withheld and filed, or recorded as not "
		"subject to withholding with the reason, and every supplier is classified."
	)
	return "".join(parts)


def withholding_check():
	"""Cron: 08:00 on the 3rd. Looks at last month. At most one task per month."""
	first_of_last = get_first_day(add_months(getdate(nowdate()), -1))
	last_of_last = get_last_day(first_of_last)
	label = first_of_last.strftime("%B %Y")

	due, unclassified = _withholding_candidates(first_of_last, last_of_last)
	if not due and not unclassified:
		return None

	return _raise_task(
		f"Withholding tax to deal with for {label}",
		_withholding_description(label, due, unclassified),
		priority="High" if due else "Medium",
	)


def withholding_check_catchup():
	"""Hourly: if today is the 3rd-6th, make sure the month's check ran."""
	if 3 <= getdate(nowdate()).day <= 6:
		withholding_check()


# ------------------------------------------------------------------ VAT watch


def _income_between(start, end) -> float:
	rows = frappe.get_all(
		"GL Entry",
		filters={
			"account": INCOME_ACCOUNT,
			"is_cancelled": 0,
			"posting_date": ["between", [start, end]],
		},
		fields=["debit", "credit"],
	)
	return sum(flt(r.credit) - flt(r.debit) for r in rows)


def vat_threshold_watch():
	"""Weekly. Silent below 75% of the ฿1.8m line; a task above it."""
	today = getdate(nowdate())
	ytd = _income_between(today.replace(month=1, day=1), today)
	rolling = _income_between(add_to_date(today, days=-364), today)
	highest = max(ytd, rolling)
	if highest < VAT_LINE * VAT_WARN_AT:
		return None

	over = highest >= VAT_LINE
	subject = (
		f"VAT registration required — income passed ฿{VAT_LINE:,.0f}"
		if over
		else f"VAT threshold {highest / VAT_LINE:.0%} reached — plan registration"
	)
	description = (
		f"Income against the ฿{VAT_LINE:,.0f} VAT registration line. "
		f"Rule: <a href=\"{DOC_URL}\">Tax</a>.<br><br>"
		f"<b>Calendar year to date:</b> ฿{ytd:,.2f} ({ytd / VAT_LINE:.1%})<br>"
		f"<b>Rolling 12 months:</b> ฿{rolling:,.2f} ({rolling / VAT_LINE:.1%})<br>"
		f"<b>Headroom on the higher reading:</b> ฿{max(VAT_LINE - highest, 0):,.2f}<br><br>"
	)
	if over:
		description += (
			"<b>Registration must happen within 30 days of the day income passed the line.</b> "
			"Find that date, then register. The day registration completes, every invoice carries "
			"VAT and the Tax doc changes — tell Finance and Account Management before it does.<br><br>"
			"<b>Done when</b> Kiluth is VAT-registered and the Tax doc is updated."
		)
	else:
		description += (
			"Not urgent yet. Plan registration now so it is never done in a hurry.<br><br>"
			"<b>Done when</b> there is a decision on when to register and who does it."
		)
	return _raise_task(subject, description, priority="Urgent" if over else "Medium")
