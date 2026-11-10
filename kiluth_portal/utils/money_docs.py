"""One layout for Kiluth's three money documents: quotation, invoice and receipt.

The print formats "Quotation Print", "Invoice Print" and "Receipt" are one line
each. They call `kiluth_money_doc(doc)` (hooks.py `jinja`), which builds the
values here, and render templates/print/money_doc.html, which holds the one
shared header, footer, item list, totals and amount in words (TASK-2026-00157).

Thai standard, Thai first with English under each label:
- the title in Thai and English, never "ใบกำกับภาษี" (Kiluth is not
  VAT-registered, so it may not issue a tax invoice: Revenue Code s.86/13)
- Kiluth's legal name, head office, address and labelled tax ID
- the number once, the date, one list, one total, the total in Thai words
  (…บาทถ้วน) and in English
- Receipt: payment date, method, reference, the invoices paid, withholding

Where the Portal has no legal name, address or tax ID for the customer, the
document says so plainly instead of leaving a gap.

The helpers above `money_doc` import nothing from Frappe, so tests can run
them alone: python3 kiluth_portal/tests/test_money_docs.py
"""

from __future__ import annotations

import base64
import html as _html
import os
import re
from datetime import date, datetime

PUBLIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")

SELLER = {
	"name_th": "บริษัท คิลุธ จำกัด",
	"name_en": "Kiluth LTD.",
	"branch_th": "สำนักงานใหญ่",
	"branch_en": "Head office",
	"address_th": "7 ถนนเพชรเกษม 54 แยก 1 แขวงบางด้วน เขตภาษีเจริญ กรุงเทพมหานคร 10160",
	"address_en": "7 Phet Kasem 54 Alley 1, Bang Duan Subdistrict, Phasi Charoen District, Bangkok 10160",
	"tax_id": "0105 5682 0019 9",
	"email": "hello@kiluth.com",
	"phone": "+66 (0) 65 484 0370",
	"web": "kiluth.com",
}

# Placeholders Poom decides later (plan 2026-11-10). The bank is settled: Hub, 10 Nov.
BANK = {"bank_th": "ธนาคารกสิกรไทย", "bank_en": "Kasikornbank (KBank)", "number": "219-1-59161-8",
	"holder_th": "บริษัท คิลุธ จำกัด", "holder_en": "Kiluth LTD.", "type_th": "ออมทรัพย์", "type_en": "Savings"}
SIGNER = {"th": "พฤทธิพันธ์ สำราญรื่น", "en": "Phuttipan Samranruen"}
TERMS_URL = "kiluth.com/terms"

TITLES = {
	"Quotation": ("ใบเสนอราคา", "Quotation"),
	"Sales Invoice": ("ใบแจ้งหนี้", "Invoice"),
	"Payment Entry": ("ใบเสร็จรับเงิน", "Receipt"),
}

METHODS = {
	"credit card": ("บัตรเครดิต", "Credit card"),
	"debit card": ("บัตรเดบิต", "Debit card"),
	"bank transfer": ("โอนเงินเข้าบัญชี", "Bank transfer"),
	"wire transfer": ("โอนเงินเข้าบัญชี", "Bank transfer"),
	"bank draft": ("โอนเงินเข้าบัญชี", "Bank transfer"),
	"promptpay": ("พร้อมเพย์", "PromptPay"),
	"cash": ("เงินสด", "Cash"),
	"cheque": ("เช็ค", "Cheque"),
}

MONTHS_TH = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# ─── Amount in words ────────────────────────────────────────────────────────

_TH_DIGITS = ("", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า")
_TH_PLACES = ("", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน")


def _th_number(n: int) -> str:
	"""A whole number in Thai words, e.g. 9350 -> เก้าพันสามร้อยห้าสิบ."""
	if n == 0:
		return "ศูนย์"
	if n >= 1_000_000:
		high, low = divmod(n, 1_000_000)
		return _th_number(high) + "ล้าน" + (_th_group(low, has_higher=True) if low else "")
	return _th_group(n, has_higher=False)


def _th_group(n: int, has_higher: bool) -> str:
	digits = [int(d) for d in str(n)][::-1]
	out = []
	for place in range(len(digits) - 1, -1, -1):
		d = digits[place]
		if not d:
			continue
		if place == 0:
			# "เอ็ด" when a higher digit is read before it: 11, 101, 1,000,001
			out.append("เอ็ด" if d == 1 and (n > 1 or has_higher) else _TH_DIGITS[d])
		elif place == 1:
			out.append({1: "", 2: "ยี่"}.get(d, _TH_DIGITS[d]) + "สิบ")
		else:
			out.append(_TH_DIGITS[d] + _TH_PLACES[place])
	return "".join(out)


def _split_satang(amount) -> tuple[int, int]:
	satang = int(round(abs(float(amount or 0)) * 100))
	return divmod(satang, 100)


def baht_words_th(amount) -> str:
	"""9350 -> เก้าพันสามร้อยห้าสิบบาทถ้วน; 48524.5 -> …บาทห้าสิบสตางค์."""
	baht, satang = _split_satang(amount)
	if not satang:
		return _th_number(baht) + "บาทถ้วน"
	return (_th_number(baht) + "บาท" if baht else "") + _th_number(satang) + "สตางค์"


_EN_ONES = ("", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
	"twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _en_below_1000(n: int) -> str:
	words = []
	if n >= 100:
		words += [_EN_ONES[n // 100], "hundred"]
		n %= 100
	if n >= 20:
		words.append(_EN_TENS[n // 10] + ("-" + _EN_ONES[n % 10] if n % 10 else ""))
	elif n:
		words.append(_EN_ONES[n])
	return " ".join(words)


def _en_number(n: int) -> str:
	if n == 0:
		return "zero"
	words = []
	for value, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (1, "")):
		if n >= value:
			words.append((_en_below_1000(n // value) + " " + name).strip())
			n %= value
	return " ".join(words)


def baht_words_en(amount) -> str:
	"""9350 -> Nine thousand three hundred fifty baht only."""
	baht, satang = _split_satang(amount)
	text = _en_number(baht) + " baht"
	if satang:
		text += " and " + _en_number(satang) + " satang"
	return text[0].upper() + text[1:] + " only"


# ─── Small formatters ───────────────────────────────────────────────────────

def money(amount) -> str:
	"""9350 -> 9,350.00 (the column says ฿ once, the rows don't repeat it)."""
	return f"{float(amount or 0):,.2f}"


def qty(value) -> str:
	v = float(value or 0)
	return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}".rstrip("0")


def _as_date(value):
	if not value:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def date_th(value) -> str:
	"""2026-11-10 -> 10 พ.ย. 2569 (Buddhist year)."""
	d = _as_date(value)
	return f"{d.day} {MONTHS_TH[d.month - 1]} {d.year + 543}" if d else ""


def date_en(value) -> str:
	d = _as_date(value)
	return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}" if d else ""


def tax_id(value) -> str:
	"""A 13-digit Thai tax ID in Kiluth's 4-4-4-1 groups; anything else as typed."""
	digits = re.sub(r"\D", "", value or "")
	if len(digits) != 13:
		return (value or "").strip()
	return f"{digits[:4]} {digits[4:8]} {digits[8:12]} {digits[12]}"


def installment(text) -> tuple[int, int] | None:
	"""'installment 2 of 3 (30%)' -> (2, 3). Thai 'งวดที่ 2/3' too."""
	m = re.search(r"(?:installment|งวดที่)\s*(\d+)\s*(?:of|/|จาก)\s*(\d+)", text or "", re.I)
	return (int(m.group(1)), int(m.group(2))) if m else None


_ALLOWED = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li"}


def clean_description(text) -> str:
	"""Item descriptions arrive as Quill HTML (`<div class="ql-editor">…`). Keep the
	paragraphs, lists and bold; drop the wrapper, classes, tabs and empty lines."""
	text = (text or "").replace("\t", " ")
	text = re.sub(r"<(/?)(\w+)[^>]*>", lambda m: f"<{m.group(1)}{m.group(2).lower()}>"
		if m.group(2).lower() in _ALLOWED else ("<br>" if m.group(2).lower() == "div" and m.group(1) else ""), text)
	text = re.sub(r"<p>\s*(<br>)?\s*</p>", "", text)
	text = re.sub(r"(\s*<br>\s*)+$", "", text.strip())
	text = re.sub(r"^(\s*<br>\s*)+", "", text)
	text = re.sub(r"\s{2,}", " ", text)
	return text.strip()


def method(mode_of_payment) -> tuple[str, str]:
	key = (mode_of_payment or "").strip().lower()
	return METHODS.get(key, (mode_of_payment or "", mode_of_payment or ""))


def reference(ref) -> str:
	"""A payment reference fit for paper: Stripe IDs say Stripe, others as typed."""
	ref = (ref or "").strip()
	if re.match(r"^(ch|pi|py|po|txn)_", ref):
		return f"Stripe {ref}"
	return ref


def is_vat(row) -> bool:
	text = f"{row.get('account_head') or ''} {row.get('description') or ''}".lower()
	return "vat" in text or "ภาษีมูลค่าเพิ่ม" in text


def is_withholding(account) -> bool:
	text = (account or "").lower()
	return "withholding" in text or "หัก ณ ที่จ่าย" in text


# ─── Fonts and logo, inline ─────────────────────────────────────────────────

# wkhtmltopdf's QtWebKit doesn't fall back from one web font to the next for
# missing glyphs: with font-family "Theinhardt, Plex Thai", Thai went straight
# to DejaVu Sans boxes, and it keeps one font per internal family, so Theinhardt
# Light and Regular can't both load (bench, 10 Nov 2026). So: one weight per
# typeface (Regular, the kiluth-document body weight), and `thai_spans` puts
# every Thai run in <span class="kt"> with the Thai font named outright.
FONTS = (("Kiluth Latin", "theinhardt-regular-webfont.ttf"), ("Kiluth Thai", "IBMPlexSansThai-Regular.ttf"))


def fonts_css() -> str:
	"""Theinhardt for Latin, IBM Plex Sans Thai for Thai and ฿, as data URIs from
	public/fonts/. Same reason as report_pdf.font_faces: the Portal's wkhtmltopdf
	can't fetch /files/, and fell back to DejaVu Sans. Own family names, so the
	"Redesign" print style's /files/ faces can't take over. The line break after
	`src:` keeps Frappe's scrub_urls from adding " !important" inside url()."""
	out = []
	for fam, f in FONTS:
		with open(os.path.join(PUBLIC, "fonts", f), "rb") as fh:
			data = base64.b64encode(fh.read()).decode()
		out.append(f"@font-face {{ font-family: '{fam}'; src:\n\t\turl(data:font/truetype;charset=utf-8;base64,{data}) "
			f"format('truetype'); font-weight: normal; font-style: normal; }}")
	return "\n".join(out)


_TAG = re.compile(r"(<[^>]*>)")
_THAI_RUN = re.compile(r"[\u0E00-\u0E7F]+(?:[ \u00A0]+[\u0E00-\u0E7F]+)*")


def thai_spans(html) -> str:
	"""Jinja filter `kiluth_thai`: wrap each run of Thai text (and ฿) in
	<span class="kt">, leaving tags and <style> alone."""
	parts = _TAG.split(str(html or ""))
	in_style = False
	for i, part in enumerate(parts):
		if part.startswith("<"):
			low = part.lower()
			in_style = low.startswith("<style") or (in_style and not low.startswith("</style"))
			continue
		if not in_style:
			parts[i] = _THAI_RUN.sub(lambda m: f'<span class="kt">{m.group(0)}</span>', part)
	return "".join(parts)


def logo_uri() -> str:
	with open(os.path.join(PUBLIC, "images", "logo-black.svg"), "rb") as f:
		return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()


def esc(x) -> str:
	return _html.escape(str(x if x is not None else ""))


# ─── The document values ────────────────────────────────────────────────────

def _items(rows, invoice=None):
	out = []
	for r in rows:
		detail = clean_description(r.get("description"))
		if re.sub(r"<[^>]+>", "", detail).strip() == (r.get("item_name") or "").strip():
			detail = ""
		out.append({"title": r.get("item_name") or r.get("item_code"), "detail": detail, "invoice": invoice,
			"qty": qty(r.get("qty")), "uom": r.get("uom") or "", "rate": money(r.get("rate")), "amount": money(r.get("amount")),
			"so": r.get("sales_order")})
	return out


def _taxes(rows):
	"""Tax rows on the record, VAT included: the paper must add up to the total.
	New documents can't carry VAT (utils/vat.py); a few older ones still do."""
	return [{"th": "ภาษีมูลค่าเพิ่ม" if is_vat(t) else (t.get("description") or ""), "en": t.get("description") or "",
		"value": money(t.get("tax_amount")), "vat": is_vat(t)} for t in rows or []]


def buyer_block(customer, address, fallback_name):
	"""The customer's legal details, with a plain placeholder for each gap."""
	customer = customer or {}
	name = (customer.get("custom_legal_name") or "").strip()
	lines = []
	if address:
		lines = [x for x in (address.get("address_line1"), address.get("address_line2"),
			" ".join(x for x in (address.get("city"), address.get("state"), address.get("pincode")) if x)) if x]
	tid = tax_id(customer.get("tax_id"))
	branch = (customer.get("custom_branch") or "").strip()
	return {
		"name": name or fallback_name,
		"name_missing": not name,
		"trade_name": fallback_name if name and name != fallback_name else "",
		"address": lines,
		"tax_id": tid,
		"branch": branch or ("สำนักงานใหญ่ / Head office" if tid else ""),
	}


def build(doc, customer=None, address=None, invoices=None):
	"""Every value the layout prints. `doc` is the Quotation, Sales Invoice or
	Payment Entry (a dict or a Frappe document); `invoices` are a receipt's
	Sales Invoices. No Frappe calls, so tests can feed plain dicts."""
	g = doc.get
	kind = g("doctype")
	th, en = TITLES[kind]
	m = {"kind": kind, "title_th": th, "title_en": en, "number": g("name"), "seller": SELLER, "bank": None,
		"meta": [], "lines": [], "taxes": [], "totals": [], "sections": [], "signatures": [], "mark": "",
		"draft": g("docstatus") == 0, "cancelled": g("docstatus") == 2}
	fallback = g("customer_name") or g("party_name") or g("customer") or g("party")
	m["buyer"] = buyer_block(customer, address, fallback)
	if not m["buyer"]["tax_id"] and g("tax_id"):
		m["buyer"]["tax_id"] = tax_id(g("tax_id"))

	def meta(label_th, label_en, value):
		if value:
			m["meta"].append((label_th, label_en, value))

	if kind == "Quotation":
		meta("เลขที่", "No.", g("name"))
		meta("วันที่", "Date", f"{date_th(g('transaction_date'))} · {date_en(g('transaction_date'))}")
		meta("ยืนราคาถึง", "Valid until", g("valid_till") and f"{date_th(g('valid_till'))} · {date_en(g('valid_till'))}")
		m["lines"] = _items(g("items") or [])
		m["taxes"] = _taxes(g("taxes"))
		total = g("grand_total")
		schedule = g("payment_schedule") or []
		terms = []
		for i, p in enumerate(schedule, 1):
			share = f"{float(p.get('invoice_portion') or 0):g}%"
			terms.append((f"งวดที่ {i} / Installment {i} of {len(schedule)}" if len(schedule) > 1 else "ชำระเต็มจำนวน / In full",
				f"{share} · ฿{money(p.get('payment_amount'))} · {date_th(p.get('due_date'))} · {date_en(p.get('due_date'))}"))
		m["sections"].append({"th": "เงื่อนไขการชำระเงิน", "en": "Payment terms", "rows": terms or
			[("—", "ตามที่ตกลง / As agreed")]})
		m["sections"].append({"th": "เงื่อนไขการให้บริการ", "en": "Terms of service", "rows": [
			("", f"ตามเงื่อนไขที่ {TERMS_URL} และข้อเสนอโครงการที่แนบ / As set out at {TERMS_URL} and in the attached proposal")]})
		m["signatures"] = [
			{"th": "ผู้เสนอราคา", "en": "Quoted by", "name_th": SIGNER["th"], "name_en": SIGNER["en"], "org": "บริษัท คิลุธ จำกัด / Kiluth LTD."},
			{"th": "ผู้อนุมัติสั่งซื้อ", "en": "Accepted by", "name_th": "", "name_en": "", "org": m["buyer"]["name"]},
		]
	elif kind == "Sales Invoice":
		m["mark"] = "ต้นฉบับ / Original"
		meta("เลขที่", "No.", g("name"))
		meta("วันที่", "Date", f"{date_th(g('posting_date'))} · {date_en(g('posting_date'))}")
		meta("ครบกำหนดชำระ", "Due date", g("due_date") and f"{date_th(g('due_date'))} · {date_en(g('due_date'))}")
		orders = sorted({r.get("sales_order") for r in g("items") or [] if r.get("sales_order")})
		meta("อ้างอิงใบสั่งขาย", "Sales order", ", ".join(orders))
		meta("อ้างอิงใบสั่งซื้อ", "PO number", g("po_no"))
		inst = next((installment(r.get("description")) for r in g("items") or [] if installment(r.get("description"))), None)
		meta("งวดที่", "Installment", inst and f"{inst[0]} จาก {inst[1]} · {inst[0]} of {inst[1]}")
		m["lines"] = _items(g("items") or [])
		m["taxes"] = _taxes(g("taxes"))
		total = g("grand_total")
		m["bank"] = BANK
		m["signatures"] = [{"th": "ผู้ออกเอกสาร", "en": "Issued by", "name_th": SIGNER["th"], "name_en": SIGNER["en"],
			"org": "บริษัท คิลุธ จำกัด / Kiluth LTD."}]
	else:
		m["mark"] = "ต้นฉบับ / Original"
		invoices = invoices or []
		meta("เลขที่", "No.", g("name"))
		meta("วันที่รับเงิน", "Payment date", f"{date_th(g('posting_date'))} · {date_en(g('posting_date'))}")
		meta("ชำระตามใบแจ้งหนี้", "For invoice", ", ".join(i.get("name") for i in invoices))
		several = len(invoices) > 1
		for inv in invoices:
			m["lines"] += _items(inv.get("items") or [], inv.get("name") if several else None)
			m["taxes"] += _taxes(inv.get("taxes"))
		invoice_total = sum(float(i.get("grand_total") or 0) for i in invoices)
		wht = sum(float(d.get("amount") or 0) for d in g("deductions") or [] if is_withholding(d.get("account")))
		paid = float(g("paid_amount") or 0)
		total = paid + wht
		mth, men = method(g("mode_of_payment"))
		pay_rows = [("วิธีชำระ / Method", f"{mth} / {men}" if mth != men else mth)]
		if g("reference_no"):
			pay_rows.append(("เลขอ้างอิง / Reference", reference(g("reference_no"))))
		if wht:
			pay_rows.append(("รับเงิน / Received", f"฿{money(paid)}"))
			pay_rows.append(("ภาษีหัก ณ ที่จ่าย / Withholding tax", f"฿{money(wht)} (ตามหนังสือรับรองการหักภาษี ณ ที่จ่าย / per the withholding certificate)"))
		m["sections"].append({"th": "การชำระเงิน", "en": "Payment", "rows": pay_rows})
		# The same facts unformatted, for the receipt styles that lay payment out
		# their own way (A: tick boxes, C: the paid band). Mockup round, 10 Nov.
		m["pay"] = {"method": men, "method_th": mth, "reference": reference(g("reference_no")),
			"date_th": date_th(g("posting_date")), "date_en": date_en(g("posting_date")),
			"invoices": [i.get("name") for i in invoices]}
		m["receipt_invoice_total"] = invoice_total
		m["signatures"] = [{"th": "ผู้รับเงิน", "en": "Received by", "name_th": SIGNER["th"], "name_en": SIGNER["en"],
			"org": "บริษัท คิลุธ จำกัด / Kiluth LTD."}]

	subtotal = sum(float(r.get("amount") or 0) for r in (g("items") or [])) if kind != "Payment Entry" \
		else sum(float(i.get("total") or 0) for i in invoices or [])
	if m["taxes"] or float(g("discount_amount") or 0):
		m["totals"].append(("รวมเป็นเงิน", "Subtotal", money(subtotal), False))
		if float(g("discount_amount") or 0):
			m["totals"].append(("ส่วนลด", "Discount", "-" + money(g("discount_amount")), False))
		for t in m["taxes"]:
			m["totals"].append((t["th"], t["en"], t["value"], False))
	if kind == "Payment Entry":
		if abs(m["receipt_invoice_total"] - total) > 0.005:
			m["totals"].append(("ยอดตามใบแจ้งหนี้", "Invoice total", money(m["receipt_invoice_total"]), False))
		if wht:
			m["totals"].append(("ภาษีหัก ณ ที่จ่าย", "Withholding tax", money(wht), False))
		m["totals"].append(("จำนวนเงินที่ได้รับ", "Amount received", money(total), True))
	else:
		m["totals"].append(("จำนวนเงินรวมทั้งสิ้น", "Total", money(total), True))
	m["total"] = money(total)
	m["words_th"] = baht_words_th(total)
	m["words_en"] = baht_words_en(total)
	m["has_vat_row"] = any(t["vat"] for t in m["taxes"])
	return m


def money_doc(doc):
	"""Jinja method `kiluth_money_doc(doc)`: looks up the customer, the address and
	a receipt's invoices, then `build`. Reads only; never saves anything."""
	import frappe

	kind = doc.doctype
	party = doc.get("party_name") if kind == "Quotation" else doc.get("customer") if kind == "Sales Invoice" else doc.get("party")
	is_customer = (kind == "Quotation" and doc.get("quotation_to") == "Customer") or kind == "Sales Invoice" \
		or (kind == "Payment Entry" and doc.get("party_type") == "Customer")
	customer = frappe.db.get_value("Customer", party, ["custom_legal_name", "tax_id", "customer_primary_address"],
		as_dict=True) if is_customer and party else None
	address_name = doc.get("customer_address") or (customer or {}).get("customer_primary_address")
	address = frappe.db.get_value("Address", address_name, ["address_line1", "address_line2", "city", "state",
		"pincode"], as_dict=True) if address_name else None
	invoices = []
	if kind == "Payment Entry":
		for ref in doc.get("references") or []:
			if ref.reference_doctype == "Sales Invoice":
				invoices.append(frappe.get_doc("Sales Invoice", ref.reference_name).as_dict())
	return build(doc.as_dict(), customer, address, invoices)
