"""Checks for the quotation, invoice and receipt layout values. No Frappe, no network:

	python3 kiluth_portal/tests/test_money_docs.py

Cases come from the Pharmdelo samples (TASK-2026-00157): receipt ACC-PAY-2026-01145
paid ฿9,350 over invoices ACC-SINV-2026-00228 (฿9,000, installment 2 of 3) and
ACC-SINV-2026-00229 (฿350 card fee).
"""

import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

from kiluth_portal.utils.money_docs import (  # noqa: E402
	baht_words_en,
	baht_words_th,
	build,
	clean_description,
	date_th,
	installment,
	method,
	reference,
	tax_id,
	thai_spans,
)

WORDS_TH = {
	0: "ศูนย์บาทถ้วน",
	1: "หนึ่งบาทถ้วน",
	11: "สิบเอ็ดบาทถ้วน",
	21: "ยี่สิบเอ็ดบาทถ้วน",
	101: "หนึ่งร้อยเอ็ดบาทถ้วน",
	350: "สามร้อยห้าสิบบาทถ้วน",
	9000: "เก้าพันบาทถ้วน",
	9350: "เก้าพันสามร้อยห้าสิบบาทถ้วน",
	72546: "เจ็ดหมื่นสองพันห้าร้อยสี่สิบหกบาทถ้วน",
	889000: "แปดแสนแปดหมื่นเก้าพันบาทถ้วน",
	1000000: "หนึ่งล้านบาทถ้วน",
	1000001: "หนึ่งล้านเอ็ดบาทถ้วน",
	21000000: "ยี่สิบเอ็ดล้านบาทถ้วน",
	48524.5: "สี่หมื่นแปดพันห้าร้อยยี่สิบสี่บาทห้าสิบสตางค์",
	0.25: "ยี่สิบห้าสตางค์",
}

WORDS_EN = {
	9350: "Nine thousand three hundred fifty baht only",
	72546: "Seventy-two thousand five hundred forty-six baht only",
	48524.5: "Forty-eight thousand five hundred twenty-four baht and fifty satang only",
	1000000: "One million baht only",
}

QUILL = ('<div class="ql-editor read-mode"><p>1.Core Feature\t</p><p><strong>1.1 Role &amp; Membership</strong> Add roles</p>'
	'<p><br></p><p>2.Standard\t</p></div>')

INV_228 = {"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00228", "docstatus": 1, "customer": "Pharmdelo",
	"customer_name": "Pharmdelo", "posting_date": "2026-11-09", "due_date": "2026-11-16", "total": 9000, "grand_total": 9000,
	"items": [{"item_name": "Software Development Service", "qty": 1, "rate": 9000, "amount": 9000, "sales_order": "SAL-ORD-2026-00002",
		"description": "Pharmdelo AI Assistant: installment 2 of 3 (30%), due after design approval"}], "taxes": []}
INV_229 = {"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00229", "total": 350, "grand_total": 350,
	"items": [{"item_name": "Software Development Service", "qty": 1, "rate": 350, "amount": 350,
		"description": "Pharmdelo AI Assistant: card payment fee for installment 2"}], "taxes": []}
PAY_1145 = {"doctype": "Payment Entry", "name": "ACC-PAY-2026-01145", "docstatus": 1, "party_type": "Customer",
	"party": "Pharmdelo", "party_name": "Pharmdelo", "posting_date": "2026-11-10", "mode_of_payment": "Credit Card",
	"paid_amount": 9350, "reference_no": "ch_3Ua861HiyA1OUNd91zq6MP3w", "deductions": []}

failures = []


def check(name, got, want):
	if got != want:
		failures.append(f"{name}: got {got!r}, want {want!r}")


for amount, want in WORDS_TH.items():
	check(f"th {amount}", baht_words_th(amount), want)
for amount, want in WORDS_EN.items():
	check(f"en {amount}", baht_words_en(amount), want)

check("date th", date_th("2026-11-10"), "10 พ.ย. 2569")
check("tax id grouped", tax_id("0105568200199"), "0105 5682 0019 9")
check("tax id as typed", tax_id("12345"), "12345")
check("installment en", installment("installment 2 of 3 (30%)"), (2, 3))
check("installment th", installment("งวดที่ 1/3"), (1, 3))
check("no installment", installment("card payment fee"), None)
check("method card", method("Credit Card"), ("บัตรเครดิต", "Credit card"))
check("stripe ref", reference("ch_3Ua861"), "Stripe ch_3Ua861")
check("bank ref", reference("KBANK 0042"), "KBANK 0042")
check("quill", clean_description(QUILL), "<p>1.Core Feature </p><p><strong>1.1 Role &amp; Membership</strong> Add roles</p><p>2.Standard </p>")

inv = build(INV_228)
check("invoice title", (inv["title_th"], inv["title_en"]), ("ใบแจ้งหนี้", "Invoice"))
check("invoice meta labels", [x[1] for x in inv["meta"]], ["No.", "Date", "Due date", "Sales order", "Installment"])
check("invoice installment", inv["meta"][-1][2], "2 จาก 3 · 2 of 3")
check("invoice one total row", inv["totals"], [("จำนวนเงินรวมทั้งสิ้น", "Total", "9,000.00", True)])
check("invoice bank", inv["bank"]["number"], "219-1-59161-8")
check("invoice placeholders", (inv["buyer"]["name"], inv["buyer"]["name_missing"], inv["buyer"]["address"], inv["buyer"]["tax_id"]),
	("Pharmdelo", True, [], ""))
check("number printed once in meta", sum(1 for x in inv["meta"] if x[2] == "ACC-SINV-2026-00228"), 1)

rc = build(PAY_1145, invoices=[INV_228, INV_229])
check("receipt title", rc["title_th"], "ใบเสร็จรับเงิน")
check("receipt items from both invoices", [i["invoice"] for i in rc["lines"]], ["ACC-SINV-2026-00228", "ACC-SINV-2026-00229"])
check("receipt totals", rc["totals"], [("จำนวนเงินที่ได้รับ", "Amount received", "9,350.00", True)])
check("receipt words", rc["words_th"], "เก้าพันสามร้อยห้าสิบบาทถ้วน")
check("receipt method", rc["sections"][0]["rows"][0], ("วิธีชำระ / Method", "บัตรเครดิต / Credit card"))
check("receipt mark", rc["mark"], "ต้นฉบับ / Original")

wht = build({**PAY_1145, "paid_amount": 8730, "deductions": [{"account": "Withholding Tax Receivable - K", "amount": 270}]},
	invoices=[INV_228])
check("withholding totals", [t[1] for t in wht["totals"]], ["Withholding tax", "Amount received"])
check("withholding settles full fee", wht["total"], "9,000.00")

short = build({**PAY_1145, "paid_amount": 48524}, invoices=[{**INV_228, "grand_total": 48524.5, "total": 48524.5}])
check("paid differs from invoices", [t[1] for t in short["totals"]], ["Invoice total", "Amount received"])

legal = build(INV_228, customer={"custom_legal_name": "บริษัท ฟาร์มเดโล จำกัด", "tax_id": "0105567169999"},
	address={"address_line1": "1 ถนนสุขุมวิท", "city": "กรุงเทพมหานคร", "pincode": "10110"})
check("legal buyer", (legal["buyer"]["name"], legal["buyer"]["trade_name"], legal["buyer"]["tax_id"], legal["buyer"]["branch"]),
	("บริษัท ฟาร์มเดโล จำกัด", "Pharmdelo", "0105 5671 6999 9", "สำนักงานใหญ่ / Head office"))

with open(os.path.join(here, "..", "templates", "print", "money_doc.html"), encoding="utf-8") as f:
	text = repr([inv, rc, wht]) + f.read()
check("never says tax invoice in Thai", "ใบกำกับภาษี" in text, False)

check("thai spans", thai_spans('<p class="x">ใบเสร็จรับเงิน / Receipt ฿9,350</p><style>.a{}</style>'),
	'<p class="x"><span class="kt">ใบเสร็จรับเงิน</span> / Receipt <span class="kt">฿</span>9,350</p><style>.a{}</style>')
check("thai spans keep spaces inside a run", thai_spans("บริษัท คิลุธ จำกัด"), '<span class="kt">บริษัท คิลุธ จำกัด</span>')

if failures:
	print("\n".join(failures))
	sys.exit(1)
print("money docs: all checks passed")
