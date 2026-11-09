"""Sales (the Commercial role) saves a Sales Order once it can select Account, on a LOCAL
THROWAWAY bench. Makes up a company, receivable account, customer and user, then deletes
them. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_commercial_account.run
"""

import json
import os

import frappe

SALES = "e2e-commercial-account@kiluth.com"
COMPANY, ABBR, CUSTOMER, ITEM = "E2E Account Co", "E2EA", "E2E Account Client", "E2E-ACCOUNT-SERVICE"
DEBTORS = f"Debtors - {ABBR}"
FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "custom_docperm.json")


def _as(user, fn):
	frappe.set_user(user)
	frappe.clear_messages()
	try:
		return fn(), None
	except (frappe.PermissionError, frappe.ValidationError) as e:
		return None, f"{type(e).__name__}: {e}"
	finally:
		frappe.set_user("Administrator")


def _fixture_row():
	rows = json.load(open(FIXTURE))
	return [r for r in rows if r["parent"] == "Account" and r["role"] == "Commercial"]


def _new_so():
	so = frappe.new_doc("Sales Order")
	so.update({"customer": CUSTOMER, "company": COMPANY, "transaction_date": "2026-11-09", "delivery_date": "2026-12-31",
	           "currency": "THB", "selling_price_list": "Standard Selling",
	           "items": [{"item_code": ITEM, "qty": 1, "rate": 100000, "delivery_date": "2026-12-31"}],
	           "payment_schedule": [{"due_date": "2026-11-30", "invoice_portion": 100, "payment_amount": 100000}]})
	return so


def run(fixture_path=None):
	global FIXTURE
	FIXTURE = fixture_path or FIXTURE
	frappe.set_user("Administrator")
	out, made = [], {"Sales Order": [], "Fiscal Year": None, "Price List": False, "UOM": False, "perm": None}
	try:
		c = frappe.new_doc("Company")
		c.name = c.company_name = COMPANY
		c.abbr, c.default_currency, c.country = ABBR, "THB", "Thailand"
		c.default_receivable_account = DEBTORS
		c.db_insert()
		a = frappe.new_doc("Account")
		a.update({"name": DEBTORS, "account_name": "Debtors", "company": COMPANY, "account_type": "Receivable",
		          "root_type": "Asset", "report_type": "Balance Sheet", "account_currency": "THB", "is_group": 0})
		a.db_insert()
		if not frappe.db.exists("Fiscal Year", "2026"):
			frappe.get_doc({"doctype": "Fiscal Year", "year": "2026", "year_start_date": "2026-01-01",
			                "year_end_date": "2026-12-31"}).insert(ignore_permissions=True)
			made["Fiscal Year"] = "2026"
		if not frappe.db.exists("Price List", "Standard Selling"):
			frappe.get_doc({"doctype": "Price List", "price_list_name": "Standard Selling", "currency": "THB",
			                "selling": 1}).insert(ignore_permissions=True)
			made["Price List"] = True
		frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
		                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
		                "territory": frappe.db.get_value("Territory", {"is_group": 0}),
		                "custom_unique_email_id": "e2e-account-client@e2e.local"}).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
			made["UOM"] = True
		frappe.get_doc({"doctype": "Item", "item_code": ITEM, "item_name": "E2E service", "is_stock_item": 0,
		                "is_sales_item": 1, "stock_uom": "Nos",
		                "item_group": frappe.db.get_value("Item Group", {"is_group": 0})}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", SALES):
			frappe.get_doc({"doctype": "User", "email": SALES, "first_name": "Cee Account", "send_welcome_email": 0,
			                "user_type": "System User", "roles": [{"role": "Commercial"}]}).insert(ignore_permissions=True)
		out.append(("the test user has only Commercial",
		            set(frappe.get_roles(SALES)) - {"All", "Guest", "Desk User"} == {"Commercial"}, frappe.get_roles(SALES)))

		# Before the fix: the failure Reaw saw on 9 Nov.
		out.append(("before: Commercial can't select Account", not frappe.has_permission("Account", "select", user=SALES), None))

		def save():
			so = _new_so()
			so.insert()
			made["Sales Order"].append(so.name)
			return so.name
		_, err = _as(SALES, save)
		out.append(("before: saving a draft Sales Order fails on Account", err is not None and "account" in err.lower(), err))

		# The fix: import the branch's Commercial row on Account, as migrate would.
		rows = _fixture_row()
		out.append(("the fixture has exactly one Commercial row on Account", len(rows) == 1, rows))
		r = rows[0]
		out.append(("that row is select only, permlevel 0",
		            r["select"] == 1 and r["permlevel"] == 0 and not any(r[k] for k in (
		                "read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export",
		                "import", "share", "print", "email", "if_owner", "impersonate", "mask")), r))
		frappe.get_doc(dict(r)).insert(ignore_permissions=True, set_name=r["name"])
		made["perm"] = r["name"]
		frappe.clear_cache(doctype="Account")

		out.append(("after: Commercial can select Account", frappe.has_permission("Account", "select", user=SALES), None))
		for ptype in ("read", "write", "create", "delete", "report", "export"):
			out.append((f"after: Commercial still can't {ptype} Account",
			            not frappe.has_permission("Account", ptype, user=SALES), None))
		_, err = _as(SALES, lambda: frappe.get_doc("Account", DEBTORS).check_permission("read"))
		out.append(("after: opening the Account record is refused", err is not None and "PermissionError" in err, err))

		name, err = _as(SALES, save)
		out.append(("after: Commercial saves a draft Sales Order", err is None, err))
		if name:
			so = frappe.db.get_value("Sales Order", name, ["docstatus", "customer", "owner"], as_dict=True)
			out.append(("it is a draft owned by the Commercial user", (so.docstatus, so.owner) == (0, SALES), so))
	finally:
		frappe.set_user("Administrator")
		for so in made["Sales Order"]:
			frappe.db.delete("Sales Order Item", {"parent": so})
			frappe.db.delete("Payment Schedule", {"parent": so})
			frappe.db.delete("Version", {"ref_doctype": "Sales Order", "docname": so})
			frappe.db.delete("Sales Order", {"name": so})
		if made["perm"]:
			frappe.db.delete("Custom DocPerm", {"name": made["perm"]})
			frappe.clear_cache(doctype="Account")
		frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": CUSTOMER})
		frappe.db.delete("Customer", {"name": CUSTOMER})
		frappe.db.delete("Item Default", {"parent": ITEM})
		frappe.db.delete("Version", {"ref_doctype": "Item", "docname": ITEM})
		frappe.db.delete("Item", {"name": ITEM})
		frappe.db.delete("Account", {"name": DEBTORS})
		frappe.db.delete("Company", {"name": COMPANY})
		if made["Fiscal Year"]:
			frappe.db.delete("Fiscal Year Company", {"parent": made["Fiscal Year"]})
			frappe.db.delete("Fiscal Year", {"name": made["Fiscal Year"]})
		if made["UOM"]:
			frappe.db.delete("UOM", {"name": "Nos"})
		if made["Price List"]:
			frappe.db.delete("Price List", {"name": "Standard Selling"})
		if frappe.db.exists("User", SALES):
			frappe.delete_doc("User", SALES, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(bool(ok) for _, ok, _ in out)}/{len(out)}")
