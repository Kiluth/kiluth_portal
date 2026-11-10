"""Print the quotation, invoice and receipt samples on a LOCAL THROWAWAY bench, from
real records saved as JSON (GET /api/resource/<doctype>/<name> on the Portal, read
only): qtn.json, sinv.json, sinv2.json (the receipt's second invoice), pay.json, in
/tmp/money-docs/. PDFs go to /tmp/money-docs/out/. Never run against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_money_docs.run

The fixture formats are inserted as "MD …" Print Formats and rolled back at the end,
so the bench keeps nothing. The bench has no such customer or invoices: the customer
comes from cust.json (or a made-up filled example), the receipt's invoices from
the JSON. Bench quirks met on 10 Nov 2026 (TASK-2026-00157): wkhtmltopdf
fetches print.bundle.css from host_name, so run `bench serve --port 8000` with
notify.localhost in /etc/hosts, and a stale assets.json may need the bundle aliased.
"""
import json

import frappe

D = "/tmp/money-docs"


def load(n):
	return json.load(open(f"{D}/{n}.json"))["data"]


# A made-up, fully filled customer, to show how Billed to grows with the data.
EXAMPLE = {
	"en": ({"custom_legal_name": "Example Company Co., Ltd.", "custom_branch": "Head Office", "tax_id": "0105599999999",
		"custom_thai_documents": 0, "customer_primary_address": "EXAMPLE-EN"},
		{"address_line1": "99 Example Tower, 12th Floor, Sukhumvit Road", "city": "Khlong Toei, Bangkok", "pincode": "10110"}),
	"th": ({"custom_legal_name": "บริษัท ตัวอย่าง จำกัด", "custom_branch": "สำนักงานใหญ่", "tax_id": "0105599999999",
		"custom_thai_documents": 1, "customer_primary_address": "EXAMPLE-TH"},
		{"address_line1": "99 อาคารตัวอย่าง ชั้น 12 ถนนสุขุมวิท", "city": "แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร", "pincode": "10110"}),
}


def run():
	frappe.set_user("Administrator")
	frappe.clear_cache()
	frappe.local.conf.host_name = "http://notify.localhost:8000"
	invoices = {d["name"]: d for d in (load("sinv"), load("sinv2"))}
	real_get_doc = frappe.get_doc
	real_get_value = frappe.db.get_value
	customer = {"now": None}

	def get_doc(*args, **kw):
		if len(args) == 2 and args[0] == "Sales Invoice" and args[1] in invoices:
			return real_get_doc(invoices[args[1]])
		return real_get_doc(*args, **kw)

	def get_value(doctype, *args, **kw):
		# The bench has no Pharmdelo and none of the new Customer fields: answer
		# from the real record (cust.json) or the made-up example instead.
		if doctype == "Customer" and args:
			return frappe._dict(customer["now"][0] if customer["now"] else load("cust"))
		if doctype == "Address" and args:
			return frappe._dict(customer["now"][1]) if customer["now"] else None
		return real_get_value(doctype, *args, **kw)

	frappe.get_doc = get_doc
	frappe.db.get_value = get_value
	rows = json.load(open("/home/frappe/kiluth_portal/kiluth_portal/fixtures/print_format.json"))
	try:
		for r in rows:
			r = {**r, "name": "MD " + r["name"], "module": None, "standard": "No"}
			r.pop("modified", None)
			if frappe.db.exists("Print Format", r["name"]):
				frappe.delete_doc("Print Format", r["name"], force=True)
			real_get_doc(r).insert(ignore_permissions=True)
		for key, fmt, out, example in (("pay", "MD Receipt", "receipt-ACC-PAY-2026-01145", None),
				("sinv", "MD Invoice Print", "invoice-ACC-SINV-2026-00228", None),
				("qtn", "MD Quotation Print", "quotation-SAL-QTN-2026-00004", None),
				("sinv", "MD Invoice Print", "invoice-example-customer", "en"),
				("sinv", "MD Invoice Print", "invoice-example-customer-thai", "th")):
			customer["now"] = EXAMPLE[example] if example else None
			data = load(key)
			doc = real_get_doc(data)
			html = frappe.get_print(doc.doctype, doc.name, fmt, doc=doc)
			open(f"{D}/out/{out}.html", "w").write(html)
			from frappe.utils.pdf import get_pdf
			pdf = get_pdf(html)
			open(f"{D}/out/{out}.pdf", "wb").write(pdf)
			print("ok", out, len(pdf))
	finally:
		frappe.get_doc = real_get_doc
		frappe.db.get_value = real_get_value
		frappe.db.rollback()
