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

from kiluth_portal.utils.financial_report import (
	COMPANY,
	_cash_balance_on,
	_fmt,
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
	from kiluth_portal.utils.report_pdf import pdf

	pdf_bytes = pdf(_render_html(period, data, doc))
	fname = f"Kiluth-Close-Report-{period['start'].strftime('%Y-%m')}.pdf"

	frappe.sendmail(
		recipients=recipients,
		subject=f"Kiluth — Close Report — {period['label']}",
		message=_email_body(period, doc.name, fname),
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


def _email_body(period: dict, task: str, fname: str) -> str:
	"""Look: kiluth_portal/utils/report_email.py (the Portal email design, 2026-10-27)."""
	from frappe.utils import get_url, get_url_to_form

	from kiluth_portal.utils.report_email import email_html

	return email_html(
		title="Close Report",
		kicker=period["label"],
		lines=[f"The books for **{period['label']}** are closed. The Close Report is attached."],
		hero="hero-close.jpg",
		assets=get_url("/assets/kiluth_portal/"),
		portal_url=get_url(),
		attachment=fname,
		button="Open the close task",
		href=get_url_to_form("Task", task),
	)


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
	# A Currency field reads 0 when nobody filled it in; a real month-end
	# bank balance of exactly 0 is not a case Kiluth has, so 0 = not entered.
	bank = float(task.get("close_bank_balance") or 0) or None

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
# Design: kiluth_portal/utils/report_pdf.py (design A, 2026-10-27).

def _render_html(period: dict, d: dict, task) -> str:
	from kiluth_portal.utils import report_pdf as rp

	muted = lambda x: f"<span class='muted'>{x}</span>"
	booked = [[r.voucher_type, str(r.n)] for r in d["booked"]]
	if booked:
		booked.append((["Total", str(sum(r.n for r in d["booked"]))], "total"))

	if d["bank"] is None:
		bank = [["Cash - K at month end", _fmt(d["cash"])], ["Bank balance at month end", "<span class='bad'>Not entered</span>"]]
		bank_note = "Enter the bank's month-end balance on the close task to complete this check."
	else:
		diff = d["cash"] - d["bank"]
		status = "<span class='good'>Matches</span>" if abs(diff) < 0.005 else f"<span class='bad'>Differs by {_fmt(diff)}</span>"
		bank = [["Cash - K at month end", _fmt(d["cash"])], ["Bank balance at month end", _fmt(d["bank"])], (["Result", status], "total")]
		bank_note = ""

	client = [[rp.esc(r.party or r.voucher_no),
		f"{_fmt(r.amt)} · " + ("certificate attached" if r.certificate else "<span class='bad'>no certificate</span>")]
		for r in d["client_wht"]]
	if client:
		client.append((["Total withheld by clients", _fmt(sum(r.amt for r in d["client_wht"]))], "total"))

	kiluth = [
		[rp.th("ภ.ง.ด.3") + " " + muted("individuals"), _fmt(d["pnd3"]) if d["pnd3"] else muted("Nothing to file")],
		[rp.th("ภ.ง.ด.53") + " " + muted("companies"), _fmt(d["pnd53"]) if d["pnd53"] else muted("Nothing to file")],
	]
	kw_note = ""
	if d["wht_unknown"]:
		kiluth.append(["Payee type not set", _fmt(d["wht_unknown"])])
		kw_note = "Set the supplier type (Individual or Company) so this amount lands on the right form."

	s = d["slips"]
	if s.n:
		salaries = [
			["Salary slips", str(s.n)],
			["Gross pay", _fmt(float(s.gross or 0))],
			[rp.th("ภ.ง.ด.1") + " " + muted("salary tax"), _fmt(d["salary_tax"]) if d["salary_tax"] else muted("Nothing to file")],
			["Social security, employee share", _fmt(d["social_security"])],
			(["Net pay", _fmt(float(s.net or 0))], "total"),
		]
		sal_note = "Kiluth pays an equal employer share of social security alongside the employee share."
	else:
		salaries, sal_note = [], ""

	w = [62, 38]
	left = [
		rp.Table("Booked this month", ["", ""], booked, 1, "Nothing booked for this month.", widths=w, right=(1,)),
		rp.Table("Portal against the bank", ["", ""], bank, 2, note=bank_note, widths=w, right=(1,)),
	]
	right = [
		rp.Table("Tax clients withheld", ["", ""], client, 3, "No client withheld tax this month.",
			"Each certificate (50 " + rp.th("ทวิ") + ") should be attached to its payment.", widths=w, right=(1,)),
		rp.Table("Tax Kiluth withheld", ["", ""], kiluth, 4, note=kw_note, widths=w, right=(1,)),
		rp.Table("Salaries", ["", ""], salaries, 5, "No salary slips for this month.", sal_note, widths=w, right=(1,)),
	]
	# Two columns on the cover when they fit (they do most months); else one column over pages.
	space = rp.CONTENT_END - rp.COVER_BODY_TOP

	def height(tables):
		# Half-width columns wrap about twice as often as the estimate assumes.
		return sum(t + sum(r) * 1.3 + n + (8 if not tb.rows else 0) for tb in tables for t, r, n in [tb.heights()])

	cover = rp.cover(rp.photo("email/hero-close.jpg"), "Close report", period["label"],
		f"The books are closed. {task.name}", top=92)
	title = f"Close report · {period['label']}"
	if height(left) <= space and height(right) <= space:
		cols = [''.join(t.render(t.rows) for t in side) for side in (left, right)]
		body = f"<table class='cols'><tr><td class='c'>{cols[0]}</td><td class='c'>{cols[1]}</td></tr></table>"
		pages = [[None, None, body]]
	else:
		for t in left + right:
			t.widths = rp.GRID[2]
		pages = rp.paginate(left + right, space, title, task.name)
	return rp.document(f"Kiluth Close Report {period['label']}", cover, pages)
