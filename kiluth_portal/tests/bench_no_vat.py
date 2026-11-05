"""No VAT rows on quotations, sales orders and invoices, on a LOCAL THROWAWAY bench.
Makes up a company, its VAT and withholding accounts, a customer and documents, then
deletes them. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_no_vat.run

The bench has no chart of accounts, fiscal year, price list or UOM, so ERPNext's own
controller steps (totals, GL entries, payment schedule) are switched off while this
runs, and links and mandatory fields aren't checked. Frappe's save, submit and cancel
still run, and so do the doc_events hooks, which is where the rule lives.
"""

import frappe

from kiluth_portal.utils.vat import no_vat_rows

COMPANY, ABBR, CUSTOMER = "E2E No VAT Co", "E2EV", "E2E No VAT Client"
VAT, WHT, TAXES = f"VAT - {ABBR}", f"Withholding Tax Payable - {ABBR}", f"Duties and Taxes - {ABBR}"
MESSAGE = "Kiluth is not VAT-registered. Remove the VAT row."
DOCTYPES = ("Quotation", "Sales Order", "Sales Invoice")
# ERPNext steps that need the full accounts setup the bench doesn't have.
STEPS = ("before_validate", "validate", "before_insert", "before_save", "on_update", "after_insert",
         "before_submit", "on_submit", "before_cancel", "on_cancel", "on_update_after_submit",
         "before_update_after_submit")


def _controllers():
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
	from erpnext.selling.doctype.quotation.quotation import Quotation
	from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
	return Quotation, SalesOrder, SalesInvoice


def _fields(doctype, vat=True, **extra):
	d = {"doctype": doctype, "company": COMPANY, "currency": "THB", "conversion_rate": 1,
	     "items": [{"item_code": "SOFTWARE", "item_name": "E2E work", "qty": 1, "rate": 1000, "uom": "Nos"}],
	     "taxes": [{"charge_type": "On Net Total", "account_head": VAT if vat else WHT, "rate": 7 if vat else -3,
	                "description": "VAT 7%" if vat else "Withholding 3%"}]}
	if doctype == "Quotation":
		d.update(quotation_to="Customer", party_name=CUSTOMER, transaction_date="2026-11-05")
	elif doctype == "Sales Order":
		d.update(customer=CUSTOMER, transaction_date="2026-11-05", delivery_date="2026-12-31")
	else:
		d.update(customer=CUSTOMER, posting_date="2026-11-05", due_date="2026-12-05")
	d.update(extra)
	return d


def _loose(doc):
	doc.flags.ignore_links = doc.flags.ignore_mandatory = doc.flags.ignore_permissions = True
	return doc


def _try(fn):
	"""fn() -> (result, None), or (None, the refusal)."""
	frappe.clear_messages()
	try:
		return fn(), None
	except frappe.ValidationError as e:
		return None, str(e)


def _insert(doc, made):
	def go():
		_loose(doc).insert()
		made.append((doc.doctype, doc.name))
		return doc.name
	return _try(go)


def _write(fields, docstatus, made):
	"""An old document, written straight to the database as it sits on the live Portal."""
	doc = frappe.get_doc(fields)
	doc.docstatus = docstatus
	doc.set_new_name()
	doc.db_insert()
	made.append((doc.doctype, doc.name))
	for i, row in enumerate(doc.get_all_children(), 1):
		row.name, row.parent, row.docstatus, row.idx = frappe.generate_hash(length=10), doc.name, docstatus, i
		row.db_insert()
	return doc.name


def _account(name, account_name, parent, is_group=0, account_type=""):
	a = frappe.new_doc("Account")
	a.update({"name": name, "account_name": account_name, "company": COMPANY, "parent_account": parent,
	          "is_group": is_group, "account_type": account_type, "root_type": "Liability", "report_type": "Balance Sheet"})
	a.db_insert()


def run():
	frappe.set_user("Administrator")
	out, made = [], []
	series = dict(frappe.db.sql("select name, current from `tabSeries`"))
	saved = {c: {s: c.__dict__[s] for s in STEPS if s in c.__dict__} for c in _controllers()}
	for c in saved:
		for s in STEPS:
			setattr(c, s, lambda self, *a, **k: None)
	try:
		# The bench has no Company or accounts; bare records are enough, shaped like live's.
		c = frappe.new_doc("Company")
		c.name = c.company_name = COMPANY
		c.abbr, c.default_currency, c.country = ABBR, "THB", "Thailand"
		c.db_insert()
		_account(TAXES, "Duties and Taxes", None, is_group=1, account_type="Tax")
		_account(VAT, "VAT", TAXES, account_type="Tax")
		_account(WHT, "Withholding Tax Payable", None)
		frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
		                "custom_unique_email_id": "e2e-no-vat-client@e2e.local"}).insert(ignore_permissions=True)
		made.append(("Customer", CUSTOMER))

		# 1 and 2. New documents, with and without VAT.
		for dt in DOCTYPES:
			name, msg = _insert(frappe.get_doc(_fields(dt)), made)
			out.append((f"a new {dt} with a VAT row is refused with the message", name is None and msg == MESSAGE, msg))
			name, msg = _insert(frappe.get_doc(_fields(dt, vat=False)), made)
			out.append((f"a new {dt} with only withholding saves", bool(name), msg))
			name, msg = _insert(frappe.get_doc(_fields(dt, taxes=[])), made)
			out.append((f"a new {dt} with no taxes saves", bool(name), msg))

		# Old documents, as the 7 paid invoices and the live VAT quotations are.
		old_si = _write(_fields("Sales Invoice", status="Paid"), 1, made)
		old_q = _write(_fields("Quotation", status="Open"), 1, made)
		draft_si = _write(_fields("Sales Invoice"), 0, made)

		# 3. Duplicate an old VAT invoice.
		name, msg = _insert(frappe.copy_doc(frappe.get_doc("Sales Invoice", old_si)), made)
		out.append(("duplicating a submitted VAT invoice is refused at save", name is None and msg == MESSAGE, msg))

		# 4. A return of it keeps the VAT row, to reverse it.
		ret = _fields("Sales Invoice", is_return=1, return_against=old_si)
		ret["items"][0]["qty"] = -1
		name, msg = _insert(frappe.get_doc(ret), made)
		out.append(("a return (is_return) with a VAT row saves", bool(name), msg))

		# A draft from before the rule can't be saved or submitted with its VAT row.
		_, msg = _try(lambda: _loose(frappe.get_doc("Sales Invoice", draft_si)).save())
		out.append(("an old VAT draft is refused when saved", msg == MESSAGE, msg))
		_, msg = _try(lambda: _loose(frappe.get_doc("Sales Invoice", draft_si)).submit())
		out.append(("...and when submitted", msg == MESSAGE and frappe.db.get_value("Sales Invoice", draft_si, "docstatus") == 0, msg))
		def fix_and_submit():
			doc = _loose(frappe.get_doc("Sales Invoice", draft_si))
			doc.taxes = []
			doc.submit()
		_, msg = _try(fix_and_submit)
		out.append(("...and submits once the row is removed", msg is None and frappe.db.get_value("Sales Invoice", draft_si, "docstatus") == 1, msg))

		# 5. Old submitted VAT documents still open, print, update and cancel.
		doc, msg = _try(lambda: frappe.get_doc("Sales Invoice", old_si).as_dict())
		out.append(("a submitted VAT invoice loads", doc is not None and doc["taxes"][0]["account_head"] == VAT, msg))
		for dt, name, fmt in (("Sales Invoice", old_si, "Invoice Print"), ("Quotation", old_q, "Quotation Print")):
			html, msg = _try(lambda: frappe.get_print(dt, name, print_format=fmt))
			if html is None:  # Kiluth's format may need data the bench lacks; the standard one shows the path.
				html, msg = _try(lambda: frappe.get_print(dt, name, print_format=f"{dt} Standard"))
				fmt = f"{dt} Standard"
			out.append((f"a submitted VAT {dt} prints ({fmt})", bool(html) and name in html, msg))
		for dt, name in (("Sales Invoice", old_si), ("Quotation", old_q)):
			_, msg = _try(lambda: no_vat_rows(frappe.get_doc(dt, name)))
			out.append((f"the hook skips a submitted VAT {dt} (docstatus 1)", msg is None, msg))
		_, msg = _try(lambda: _loose(frappe.get_doc("Sales Invoice", old_si)).save())
		out.append(("update after submit on a VAT invoice doesn't trip it", msg is None, msg))
		_, msg = _try(lambda: _loose(frappe.get_doc("Sales Invoice", old_si)).cancel())
		out.append(("a submitted VAT invoice cancels", msg is None and frappe.db.get_value("Sales Invoice", old_si, "docstatus") == 2, msg))
		_, msg = _try(lambda: no_vat_rows(frappe.get_doc("Sales Invoice", old_si)))
		out.append(("the hook skips a cancelled VAT invoice (docstatus 2)", msg is None, msg))

		# Amend: a new draft copied from the cancelled one.
		amended = frappe.copy_doc(frappe.get_doc("Sales Invoice", old_si))
		amended.amended_from = old_si
		name, msg = _insert(amended, made)
		out.append(("amending a cancelled VAT invoice is refused while the row stays", name is None and msg == MESSAGE, msg))
		amended = frappe.copy_doc(frappe.get_doc("Sales Invoice", old_si))
		amended.amended_from, amended.taxes = old_si, []
		name, msg = _insert(amended, made)
		out.append(("...and saves without it", bool(name), msg))
	finally:
		for c, methods in saved.items():
			for s in STEPS:
				delattr(c, s)
			for s, fn in methods.items():
				setattr(c, s, fn)
		frappe.set_user("Administrator")
		for dt, name in made:
			for t in frappe.get_meta(dt).get_table_fields():
				frappe.db.delete(t.options, {"parent": name, "parenttype": dt})
			frappe.db.delete("Version", {"ref_doctype": dt, "docname": name})
			frappe.db.delete("Comment", {"reference_doctype": dt, "reference_name": name})
			frappe.db.delete(dt, {"name": name})
		frappe.db.delete("Account", {"company": COMPANY})
		frappe.db.delete("Company", {"name": COMPANY})
		for key, current in frappe.db.sql("select name, current from `tabSeries`"):
			if key not in series:
				frappe.db.sql("delete from `tabSeries` where name = %s", key)
			elif series[key] != current:
				frappe.db.sql("update `tabSeries` set current = %s where name = %s", (series[key], key))
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(bool(ok) for _, ok, _ in out)}/{len(out)}")
