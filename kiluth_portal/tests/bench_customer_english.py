"""A customer's name must be English, on a LOCAL THROWAWAY bench. Makes up customers
and leads, then deletes them. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_customer_english.run
"""

import frappe

THAI = "บริษัท ทดสอบอีทูอี จำกัด"
SALES = "e2e-sales@kiluth.com"


def _new(name, user="Administrator", set_name=None, **fields):
	"""Insert a customer as `user`. Returns (name, None) or (None, the refusal)."""
	frappe.set_user(user)
	frappe.clear_messages()
	try:
		doc = frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company",
		                      "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
		                      "territory": frappe.db.get_value("Territory", {"is_group": 0}),
		                      "custom_unique_email_id": f"{frappe.generate_hash(length=8)}@e2e.local", **fields})
		doc.insert(ignore_permissions=True, set_name=set_name)
		return doc.name, None
	except frappe.ValidationError as e:
		return None, str(e)
	finally:
		frappe.set_user("Administrator")


def _save(name, **fields):
	frappe.clear_messages()
	try:
		doc = frappe.get_doc("Customer", name)
		doc.update(fields)
		doc.save(ignore_permissions=True)
		return None
	except frappe.ValidationError as e:
		return str(e)


def _refused(msg):
	return bool(msg) and "English company name" in msg and "Legal name (for documents)" in msg


def run():
	frappe.set_user("Administrator")
	out, customers, leads = [], [], []
	try:
		name, msg = _new(THAI, SALES)
		out.append(("a salesperson's Thai name is refused, pointing to Legal name", name is None and _refused(msg), msg))
		name, msg = _new(THAI)
		out.append(("an admin's Thai name is refused too", name is None and _refused(msg), msg))

		name, msg = _new("E2E Mary Manufacturing Co., Ltd.", SALES, custom_legal_name=THAI)
		customers.append(name)
		out.append(("English name with a Thai Legal name saves",
		            name and frappe.db.get_value("Customer", name, "custom_legal_name") == THAI, msg))
		name, msg = _new("E2E Café O'Brien & Sons (HQ) - 2/1")
		customers.append(name)
		out.append(("punctuation and accented Latin save", bool(name), msg))
		name, msg = _new("E2E English Name", set_name="ลูกค้าอีทูอี")
		customers.append(name)
		out.append(("an English name with a Thai ID is refused", name is None and _refused(msg), msg))

		# A customer from before the rule, with a Thai name, as Mary Manufacturing was.
		old = frappe.new_doc("Customer")
		old.name = old.customer_name = "บริษัท อีทูอี เก่า จำกัด"
		old.customer_type = "Company"
		old.custom_unique_email_id = "e2e-old@e2e.local"
		old.db_insert()
		customers.append(old.name)
		msg = _save(old.name, custom_legal_name="บริษัท อีทูอี เก่า จำกัด")
		out.append(("an existing Thai-named customer still saves when its name isn't changed", msg is None, msg))
		msg = _save(old.name, customer_name="E2E Old Co., Ltd.")
		out.append(("...and its name can be changed to English", msg is None, msg))
		msg = _save(customers[0], customer_name="ทดสอบ")
		out.append(("changing an English name to Thai is refused", _refused(msg), msg))

		name, msg = _new("E2E Mary Manufacturing Company", SALES)
		customers.append(name)
		out.append(("the duplicate check still runs first", name is None and msg and "already exists" in msg, msg))

		# ERPNext's Lead -> Customer: a Thai company name on the lead now needs an English one.
		from erpnext.crm.doctype.lead.lead import make_customer
		for company, email in ((THAI, "e2e-thai-lead@e2e.local"), ("E2E Lead Company", "e2e-en-lead@e2e.local")):
			lead = frappe.get_doc({"doctype": "Lead", "first_name": "E2E", "company_name": company, "email_id": email}).insert(ignore_permissions=True)
			leads.append(lead.name)
		results = []
		for lead in leads:
			doc = make_customer(lead)
			doc.customer_group = doc.customer_group or frappe.db.get_value("Customer Group", {"is_group": 0})
			doc.territory = doc.territory or frappe.db.get_value("Territory", {"is_group": 0})
			doc.custom_unique_email_id = f"{frappe.generate_hash(length=8)}@e2e.local"
			try:
				doc.insert(ignore_permissions=True)
				customers.append(doc.name)
				results.append(None)
			except frappe.ValidationError as e:
				results.append(str(e))
		out.append(("Lead with a Thai company -> Customer is refused with the message", _refused(results[0]), results[0]))
		out.append(("Lead with an English company -> Customer works", results[1] is None, results[1]))
	finally:
		frappe.set_user("Administrator")
		# Leads first: deleting one looks up the customer made from it.
		for lead in leads:
			frappe.db.delete("Comment", {"reference_doctype": "Lead", "reference_name": lead})
			frappe.delete_doc("Lead", lead, force=True, ignore_permissions=True)
		for c in filter(None, customers):
			frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": c})
			frappe.db.delete("Version", {"ref_doctype": "Customer", "docname": c})
			frappe.db.delete("Customer", {"name": c})
		for contact in frappe.get_all("Contact", filters={"email_id": ["like", "e2e-%-lead@e2e.local"]}, pluck="name"):
			frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(bool(ok) for _, ok, _ in out)}/{len(out)}")
