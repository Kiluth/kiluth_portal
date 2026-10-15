"""Monthly Close Report — PDF built from the books when a close task completes.

Implements docs.kiluth.com/finance/monthly-close ("The Close Report"). When a
Task titled "Close the books for <Month YYYY>" moves to Completed, this builds
a one-page PDF for that month straight from the ledger and emails it to
finance@kiluth.com, and attaches the same PDF to the task.

Nothing in the report is typed by a person except the bank's month-end balance,
which Finance enters in the task's `close_bank_balance` field (Custom Field,
fixtures). Everything else is read from GL Entry, Payment Entry and Salary Slip.

Runs in the background (frappe.enqueue) so a slow PDF render or a mail error
can never block saving the task.

Manual test (System Manager), sends only to the given address:

    await frappe.call({
        method: 'kiluth_portal.utils.close_report.send_close_report',
        args: {task: 'TASK-2026-00029', recipients: ['poom.pengcharoen@kiluth.com']}
    })
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe.utils.pdf import get_pdf

from kiluth_portal.utils.financial_report import (
	COMPANY,
	FOOTER,
	LETTER_HEAD,
	_cash_balance_on,
	_fmt,
	_font_face_block,
)

RECIPIENTS = ("finance@kiluth.com",)
SUBJECT_PREFIX = "Close the books for "
CLIENT_WHT_ACCOUNT = "Tax Assets - K"  # tax clients withhold from Kiluth
KILUTH_WHT_ACCOUNT = "Withholding Tax Payable - K"  # tax Kiluth withholds from others
SALARY_TAX_COMPONENTS = ("Income Tax", "Withholding Tax")
SOCIAL_SECURITY_COMPONENT = "Social Security"


# ─── Hook ───────────────────────────────────────────────────────────────────

def on_task_update(doc, method=None):
	"""Task on_update: queue the report when a close task becomes Completed."""
	if not (doc.subject or "").startswith(SUBJECT_PREFIX):
		return
	if doc.status != "Completed":
		return
	before = doc.get_doc_before_save()
	if before and before.status == "Completed":
		return
	frappe.enqueue(
		"kiluth_portal.utils.close_report.send_close_report",
		queue="short",
		enqueue_after_commit=True,
		task=doc.name,
	)


# ─── Entry point ────────────────────────────────────────────────────────────

@frappe.whitelist()
def send_close_report(task: str, recipients: list[str] | str | None = None):
	if frappe.session.user != "Administrator" and not frappe.has_permission("Server Script", "write"):
		frappe.throw("Not permitted to send the close report.")

	if recipients is None:
		recipients = list(RECIPIENTS)
	elif isinstance(recipients, str):
		r = recipients.strip()
		recipients = frappe.parse_json(r) if r.startswith("[") else [r]

	doc = frappe.get_doc("Task", task)
	period = _period_from_subject(doc.subject)
	if not period:
		frappe.throw(f"Can't read a month from the task title: {doc.subject}")

	data = _collect(period, doc)
	pdf_bytes = get_pdf(_render_html(period, data, doc))
	fname = f"Kiluth-Close-Report-{period['start'].strftime('%Y-%m')}.pdf"

	frappe.sendmail(
		recipients=recipients,
		subject=f"Kiluth — Close Report — {period['label']}",
		message=(
			f"<p>The books for <strong>{period['label']}</strong> are closed. "
			f"The Close Report is attached.</p>"
			f"<p>{frappe.utils.get_link_to_form('Task', doc.name, 'Open the close task')}</p>"
			f"<p>— Kiluth Portal</p>"
		),
		attachments=[{"fname": fname, "fcontent": pdf_bytes}],
		delayed=False,
	)

	frappe.get_doc({
		"doctype": "File",
		"file_name": fname,
		"attached_to_doctype": "Task",
		"attached_to_name": doc.name,
		"is_private": 1,
		"content": pdf_bytes,
	}).insert(ignore_permissions=True)

	return {"period": period["label"], "recipients": recipients}


# ─── Period ─────────────────────────────────────────────────────────────────

def _period_from_subject(subject: str) -> dict | None:
	text = (subject or "")[len(SUBJECT_PREFIX):].strip()
	text = text.split("(")[0].strip()  # tolerate "(TEST)" and similar suffixes
	try:
		start = datetime.datetime.strptime(text, "%B %Y").date()
	except ValueError:
		return None
	end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
	return {"start": start, "end": end, "label": start.strftime("%B %Y")}


# ─── Data ───────────────────────────────────────────────────────────────────

def _collect(period: dict, task) -> dict:
	start, end = period["start"], period["end"]

	booked = frappe.db.sql(
		"""
		SELECT voucher_type, COUNT(DISTINCT voucher_no) AS n
		FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0 AND posting_date BETWEEN %s AND %s
		GROUP BY voucher_type ORDER BY n DESC
		""",
		(COMPANY, start, end),
		as_dict=True,
	)

	cash = _cash_balance_on(end)
	bank = task.get("close_bank_balance")
	bank = float(bank) if bank not in (None, "") else None

	client_wht = frappe.db.sql(
		"""
		SELECT voucher_type, voucher_no, party, SUM(debit - credit) AS amt
		FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0 AND account = %s
			AND posting_date BETWEEN %s AND %s
		GROUP BY voucher_type, voucher_no, party
		HAVING amt > 0
		""",
		(COMPANY, CLIENT_WHT_ACCOUNT, start, end),
		as_dict=True,
	)
	for row in client_wht:
		row["certificate"] = bool(frappe.db.exists(
			"File", {"attached_to_doctype": row.voucher_type, "attached_to_name": row.voucher_no}
		))
		if not row.party and row.voucher_type == "Payment Entry":
			row.party = frappe.db.get_value("Payment Entry", row.voucher_no, "party")

	kiluth_wht = frappe.db.sql(
		"""
		SELECT voucher_type, voucher_no, party_type, party, SUM(credit - debit) AS amt
		FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0 AND account = %s
			AND posting_date BETWEEN %s AND %s
		GROUP BY voucher_type, voucher_no, party_type, party
		HAVING amt > 0
		""",
		(COMPANY, KILUTH_WHT_ACCOUNT, start, end),
		as_dict=True,
	)
	pnd3 = pnd53 = unknown = 0.0
	for row in kiluth_wht:
		party_type, party = row.party_type, row.party
		if not party and row.voucher_type == "Payment Entry":
			party_type, party = frappe.db.get_value("Payment Entry", row.voucher_no, ["party_type", "party"])
		kind = frappe.db.get_value("Supplier", party, "supplier_type") if party_type == "Supplier" and party else None
		if kind == "Individual":
			pnd3 += row.amt
		elif kind == "Company":
			pnd53 += row.amt
		else:
			unknown += row.amt

	slips = frappe.db.sql(
		"""
		SELECT COUNT(*) AS n, SUM(gross_pay) AS gross, SUM(net_pay) AS net
		FROM `tabSalary Slip`
		WHERE docstatus = 1 AND company = %s AND start_date BETWEEN %s AND %s
		""",
		(COMPANY, start, end),
		as_dict=True,
	)[0]
	deductions = dict(frappe.db.sql(
		"""
		SELECT sd.salary_component, SUM(sd.amount)
		FROM `tabSalary Detail` sd JOIN `tabSalary Slip` ss ON ss.name = sd.parent
		WHERE ss.docstatus = 1 AND ss.company = %s AND ss.start_date BETWEEN %s AND %s
			AND sd.parentfield = 'deductions'
		GROUP BY sd.salary_component
		""",
		(COMPANY, start, end),
	))

	return {
		"booked": booked,
		"cash": cash,
		"bank": bank,
		"client_wht": client_wht,
		"pnd3": pnd3,
		"pnd53": pnd53,
		"wht_unknown": unknown,
		"slips": slips,
		"salary_tax": sum(float(deductions.get(c) or 0) for c in SALARY_TAX_COMPONENTS),
		"social_security": float(deductions.get(SOCIAL_SECURITY_COMPONENT) or 0),
	}


# ─── HTML ───────────────────────────────────────────────────────────────────

def _section(title: str, rows: list[tuple[str, str]], note: str = "") -> str:
	body = "".join(
		f"<tr><td style='padding: 5px 0; border-bottom: 0.5pt solid #e8e8e8;'>{label}</td>"
		f"<td style='padding: 5px 0; border-bottom: 0.5pt solid #e8e8e8; text-align: right;'>{value}</td></tr>"
		for label, value in rows
	)
	note_html = f"<div style='font-size: 8.5pt; color: #6b7785; margin-top: 4px;'>{note}</div>" if note else ""
	return (
		f"<div style='margin-top: 18px;'>"
		f"<div style='font-size: 9pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; "
		f"border-bottom: 1pt solid #1a1a1a; padding-bottom: 4px;'>{title}</div>"
		f"<table style='width: 100%; border-collapse: collapse; font-size: 10pt;'>{body}</table>{note_html}</div>"
	)


def _render_html(period: dict, d: dict, task) -> str:
	booked_rows = [(r.voucher_type, str(r.n)) for r in d["booked"]] or [("Nothing booked for this month", "—")]
	total = sum(r.n for r in d["booked"])
	if d["booked"]:
		booked_rows.append(("<b>Total</b>", f"<b>{total}</b>"))

	if d["bank"] is None:
		bank_rows = [("Cash - K at month end", _fmt(d["cash"])), ("Bank balance at month end", "Not entered on the task")]
		bank_note = "Enter the bank's month-end balance on the close task to complete this check."
	else:
		diff = d["cash"] - d["bank"]
		status = "Matches" if abs(diff) < 0.005 else f"Differs by {_fmt(diff)}"
		bank_rows = [
			("Cash - K at month end", _fmt(d["cash"])),
			("Bank balance at month end", _fmt(d["bank"])),
			("<b>Result</b>", f"<b>{status}</b>"),
		]
		bank_note = ""

	if d["client_wht"]:
		cw_rows = [
			(f"{r.party or r.voucher_no}", f"{_fmt(r.amt)} · {'certificate attached' if r.certificate else '<b>no certificate</b>'}")
			for r in d["client_wht"]
		]
		cw_rows.append(("<b>Total withheld by clients</b>", f"<b>{_fmt(sum(r.amt for r in d['client_wht']))}</b>"))
	else:
		cw_rows = [("No client withheld tax this month", "—")]

	kw_rows = [
		("ภ.ง.ด.3 — withheld from individuals", _fmt(d["pnd3"]) if d["pnd3"] else "Nothing to file"),
		("ภ.ง.ด.53 — withheld from companies", _fmt(d["pnd53"]) if d["pnd53"] else "Nothing to file"),
	]
	kw_note = ""
	if d["wht_unknown"]:
		kw_rows.append(("Payee type not set", _fmt(d["wht_unknown"])))
		kw_note = "Set the supplier type (Individual or Company) so this amount lands on the right form."

	s = d["slips"]
	if s.n:
		sal_rows = [
			("Salary slips", str(s.n)),
			("Gross pay", _fmt(float(s.gross or 0))),
			("ภ.ง.ด.1 — salary tax withheld", _fmt(d["salary_tax"]) if d["salary_tax"] else "Nothing to file"),
			("Social security — employee share", _fmt(d["social_security"])),
			("Net pay", _fmt(float(s.net or 0))),
		]
		sal_note = "Kiluth pays an equal employer share of social security alongside the employee share."
	else:
		sal_rows = [("No salary slips for this month", "—")]
		sal_note = ""

	style = _font_face_block() + """
		@page { size: A4; margin: 16mm 14mm 22mm 14mm; }
		body { font-family: 'Theinhardt', 'IBM Plex Sans Thai', 'Inter', Arial, sans-serif; color: #1a1a1a; font-size: 10pt; line-height: 1.45; margin: 0; }
		h1 { font-size: 22pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin: 12pt 0 4pt 0; }
		.sub { font-size: 9pt; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7785; }
		.page-footer { margin-top: 28px; padding-top: 10px; border-top: 0.5pt solid #e8e8e8; }
	"""
	body = f"""
	{LETTER_HEAD}
	<h1>Close Report</h1>
	<div class="sub">{period['label']} · Kiluth LTD. · {task.name}</div>
	{_section("1. Booked this month", booked_rows)}
	{_section("2. Portal against the bank", bank_rows, bank_note)}
	{_section("3. Tax clients withheld from Kiluth", cw_rows, "Each certificate (50 ทวิ) should be attached to its payment.")}
	{_section("4. Tax Kiluth withheld from suppliers", kw_rows, kw_note)}
	{_section("5. Salaries", sal_rows, sal_note)}
	<div class="page-footer">{FOOTER}</div>
	"""
	return f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{style}</style></head><body>{body}</body></html>"
