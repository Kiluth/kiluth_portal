"""One layout for Kiluth's three money documents: quotation, invoice and receipt.

The print formats "Quotation Print", "Invoice Print" and "Receipt" are one line
each. They call `kiluth_money_doc(doc)` (hooks.py `jinja`), which builds the
values here, and render templates/print/money_doc.html (TASK-2026-00157).

Style D, Poom's pick (10 Nov): clean, like a Stripe or Apple receipt.
- English by default; a customer with "Thai documents" ticked gets Thai, same layout
- the amount first, in one big line, with the date, method or due date under it
- From and Billed to; each customer line prints only when the Portal has it
- description and amount, the total, the total in words
- no signatures and no footer; never "ใบกำกับภาษี" (Kiluth is not
  VAT-registered, so it may not issue a tax invoice: Revenue Code s.86/13)

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

# The bank account: settled by Hub, 10 Nov.
BANK = {"bank_th": "ธนาคารกสิกรไทย", "bank_en": "Kasikornbank (KBank)", "number": "219-1-59161-8",
	"holder_th": "บริษัท คิลุธ จำกัด", "holder_en": "Kiluth LTD.", "type_th": "ออมทรัพย์", "type_en": "Savings"}

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
	"""9350 -> Nine thousand three hundred fifty baht."""
	baht, satang = _split_satang(amount)
	text = _en_number(baht) + " baht"
	if satang:
		text += " and " + _en_number(satang) + " satang"
	return text[0].upper() + text[1:]


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
# A space right after a Thai run goes inside the span: left to the Latin font,
# wkhtmltopdf drew it almost zero-wide ("เลขที่บัญชี219", bench 10 Nov).
_THAI_RUN = re.compile(r"[\u0E00-\u0E7F]+(?:[ \u00A0]+[\u0E00-\u0E7F]+)*[ \u00A0]?")


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

# Every printed word, English and Thai. A customer with "Thai documents" ticked
# gets the Thai column, same layout; everyone else gets English (Poom, 10 Nov).
WORDS = {
	"en": {"no": "No.", "date": "Date", "from": "From", "to": "Billed to", "tax_id": "Tax ID",
		"description": "Description", "amount": "Amount", "subtotal": "Subtotal", "discount": "Discount",
		"vat": "VAT", "wht": "Withholding tax", "invoice_total": "Invoice total",
		"total": {"Quotation": "Total", "Sales Invoice": "Total due", "Payment Entry": "Total received"},
		"received": "฿{amount} received", "paid_by": "Paid by {method} on {date}", "ref": "Ref {ref}",
		"due_on": "Due {date}", "headline": "฿{amount}",
		"valid": "Valid until {date}", "installment": "Installment {n} of {of}",
		"pay_to": "Pay by bank transfer", "bank_line": "{bank}, account {number}", "holder": "Account name {holder}",
		"terms": "Payment terms", "in_full": "In full", "as_agreed": "As agreed",
		"draft": "Draft, not valid", "cancelled": "Cancelled", "qty": "{qty} × ฿{rate}"},
	"th": {"no": "เลขที่", "date": "วันที่", "from": "ผู้ออกเอกสาร", "to": "ลูกค้า", "tax_id": "เลขประจำตัวผู้เสียภาษี",
		"description": "รายการ", "amount": "จำนวนเงิน", "subtotal": "รวมเป็นเงิน", "discount": "ส่วนลด",
		"vat": "ภาษีมูลค่าเพิ่ม", "wht": "ภาษีหัก ณ ที่จ่าย", "invoice_total": "ยอดตามใบแจ้งหนี้",
		"total": {"Quotation": "รวมทั้งสิ้น", "Sales Invoice": "ยอดที่ต้องชำระ", "Payment Entry": "ยอดรับชำระ"},
		"received": "รับชำระ ฿{amount}", "paid_by": "ชำระด้วย{method} วันที่ {date}", "ref": "เลขอ้างอิง {ref}",
		"due_on": "ครบกำหนดชำระ {date}", "headline": "฿{amount}",
		"valid": "ยืนราคาถึง {date}", "installment": "งวดที่ {n} จาก {of}",
		"pay_to": "ชำระโดยโอนเข้าบัญชี", "bank_line": "{bank} เลขที่บัญชี {number}", "holder": "ชื่อบัญชี {holder}",
		"terms": "เงื่อนไขการชำระเงิน", "in_full": "ชำระเต็มจำนวน", "as_agreed": "ตามที่ตกลง",
		"draft": "ฉบับร่าง ใช้อ้างอิงไม่ได้", "cancelled": "ยกเลิก", "qty": "{qty} × ฿{rate}"},
}

TITLES = {
	"Quotation": {"en": "Quotation", "th": "ใบเสนอราคา"},
	"Sales Invoice": {"en": "Invoice", "th": "ใบแจ้งหนี้"},
	"Payment Entry": {"en": "Receipt", "th": "ใบเสร็จรับเงิน"},
}


def paid_by(mode_of_payment, lang) -> str:
	"""'Credit Card' -> 'card' (en) or 'บัตรเครดิต' (th), for "Paid by card on …"."""
	th, en = method(mode_of_payment)
	if lang == "th":
		return th
	return "card" if en.endswith(" card") else en if en == "PromptPay" else en.lower()


def _items(rows, w):
	out = []
	for r in rows:
		detail = clean_description(r.get("description"))
		if re.sub(r"<[^>]+>", "", detail).strip() == (r.get("item_name") or "").strip():
			detail = ""
		q = float(r.get("qty") or 0)
		out.append({"title": r.get("item_name") or r.get("item_code"), "detail": detail, "amount": money(r.get("amount")),
			# Services are one line, one amount; quantity shows only when there's more than one.
			"qty": w["qty"].format(qty=qty(q), rate=money(r.get("rate"))) if q and q != 1 else ""})
	return out


def buyer_block(customer, address, fallback_name, w):
	"""Billed to: legal name (with its branch), address, tax ID. Each line only
	when the Portal has it; no placeholders (Poom, 10 Nov)."""
	customer = customer or {}
	name = (customer.get("custom_legal_name") or "").strip() or fallback_name
	branch = (customer.get("custom_branch") or "").strip()
	address_lines = []
	if address:
		address_lines = [x for x in (address.get("address_line1"), address.get("address_line2"),
			" ".join(x for x in (address.get("city"), address.get("state"), address.get("pincode")) if x)) if x]
	tid = tax_id(customer.get("tax_id"))
	return {"name": name, "branch": branch, "address": address_lines,
		"tax_id": f"{w['tax_id']} {tid}" if tid else ""}


def seller_block(lang, w):
	s = SELLER
	return {"name": s[f"name_{lang}"], "address": [s[f"address_{lang}"]],
		"tax_id": f"{w['tax_id']} {s['tax_id']} ({s[f'branch_{lang}']})"}


def build(doc, customer=None, address=None, invoices=None, lang=None):
	"""Every value the layout prints. `doc` is the Quotation, Sales Invoice or
	Payment Entry (a dict or a Frappe document); `invoices` are a receipt's
	Sales Invoices. `lang` is "th" when the customer has "Thai documents" ticked,
	else English. No Frappe calls, so tests can feed plain dicts."""
	g = doc.get
	kind = g("doctype")
	lang = lang or ("th" if (customer or {}).get("custom_thai_documents") else "en")
	w = WORDS[lang]
	day = date_th if lang == "th" else date_en
	m = {"kind": kind, "lang": lang, "w": w, "title": TITLES[kind][lang], "number": g("name"),
		"seller": seller_block(lang, w), "lines": [], "totals": [], "headline": "", "sub": [], "blocks": [],
		"draft": g("docstatus") == 0, "cancelled": g("docstatus") == 2}
	fallback = g("customer_name") or g("party_name") or g("customer") or g("party")
	m["buyer"] = buyer_block(customer, address, fallback, w)
	if not m["buyer"]["tax_id"] and g("tax_id"):
		m["buyer"]["tax_id"] = f"{w['tax_id']} {tax_id(g('tax_id'))}"

	taxes = []
	if kind == "Payment Entry":
		invoices = invoices or []
		for inv in invoices:
			m["lines"] += _items(inv.get("items") or [], w)
			taxes += inv.get("taxes") or []
		subtotal = sum(float(i.get("total") or 0) for i in invoices)
		invoice_total = sum(float(i.get("grand_total") or 0) for i in invoices)
		wht = sum(float(d.get("amount") or 0) for d in g("deductions") or [] if is_withholding(d.get("account")))
		total = float(g("paid_amount") or 0) + wht
		m["date"] = day(g("posting_date"))
		m["headline"] = w["received"].format(amount=money(total))
		m["sub"].append(w["paid_by"].format(method=paid_by(g("mode_of_payment"), lang), date=m["date"]))
		if g("reference_no"):
			m["sub"].append(w["ref"].format(ref=(g("reference_no") or "").strip()))
	else:
		m["lines"] = _items(g("items") or [], w)
		taxes = g("taxes") or []
		subtotal = sum(float(r.get("amount") or 0) for r in g("items") or [])
		total = float(g("grand_total") or 0)
		if kind == "Quotation":
			m["date"] = day(g("transaction_date"))
			m["headline"] = w["headline"].format(amount=money(total))
			if g("valid_till"):
				m["sub"].append(w["valid"].format(date=day(g("valid_till"))))
			schedule = g("payment_schedule") or []
			rows = []
			for i, p in enumerate(schedule, 1):
				label = w["installment"].format(n=i, of=len(schedule)) if len(schedule) > 1 else w["in_full"]
				share = f"{float(p.get('invoice_portion') or 0):g}%"
				rows.append((label, f"{share} · ฿{money(p.get('payment_amount'))}", w["due_on"].format(date=day(p.get("due_date")))))
			m["blocks"].append({"label": w["terms"], "rows": rows or [(w["as_agreed"], "", "")]})
		else:
			m["date"] = day(g("posting_date"))
			# Only the total: a "due" headline turns wrong once the invoice is paid, and
			# the receipt is the proof of payment (money-docs launch, Poom 11 Nov).
			m["headline"] = w["headline"].format(amount=money(total))
			if g("due_date"):
				m["sub"].append(w["due_on"].format(date=day(g("due_date"))))
			inst = next((installment(r.get("description")) for r in g("items") or [] if installment(r.get("description"))), None)
			if inst:
				m["sub"].append(w["installment"].format(n=inst[0], of=inst[1]))
			m["blocks"].append({"label": w["pay_to"], "rows": [
				(w["bank_line"].format(bank=BANK[f"bank_{lang}"], number=BANK["number"]), "", ""),
				(w["holder"].format(holder=BANK[f"holder_{lang}"]), "", "")]})

	# Tax rows stay only where the record has them, so old documents still add up
	# (a June quotation carries 7% VAT). New documents can't carry VAT (utils/vat.py).
	discount = float(g("discount_amount") or 0) if kind != "Payment Entry" else 0
	if taxes or discount:
		m["totals"].append((w["subtotal"], money(subtotal)))
		if discount:
			m["totals"].append((w["discount"], "-" + money(discount)))
		for t in taxes:
			m["totals"].append((w["vat"] if is_vat(t) else (t.get("description") or ""), money(t.get("tax_amount"))))
	if kind == "Payment Entry":
		if abs(invoice_total - total) > 0.005:
			m["totals"].append((w["invoice_total"], money(invoice_total)))
		if wht:
			m["totals"].append((w["wht"], money(wht)))
	m["total_label"] = w["total"][kind]
	m["total"] = money(total)
	m["words"] = baht_words_th(total) if lang == "th" else baht_words_en(total)
	return m


def money_doc(doc):
	"""Jinja method `kiluth_money_doc(doc)`: looks up the customer, the address and
	a receipt's invoices, then `build`. Reads only; never saves anything."""
	import frappe

	kind = doc.doctype
	party = doc.get("party_name") if kind == "Quotation" else doc.get("customer") if kind == "Sales Invoice" else doc.get("party")
	is_customer = (kind == "Quotation" and doc.get("quotation_to") == "Customer") or kind == "Sales Invoice" \
		or (kind == "Payment Entry" and doc.get("party_type") == "Customer")
	customer = frappe.db.get_value("Customer", party, ["custom_legal_name", "custom_branch", "custom_thai_documents",
		"tax_id", "customer_primary_address"], as_dict=True) if is_customer and party else None
	address_name = doc.get("customer_address") or (customer or {}).get("customer_primary_address")
	address = frappe.db.get_value("Address", address_name, ["address_line1", "address_line2", "city", "state",
		"pincode"], as_dict=True) if address_name else None
	invoices = []
	if kind == "Payment Entry":
		for ref in doc.get("references") or []:
			if ref.reference_doctype == "Sales Invoice":
				invoices.append(frappe.get_doc("Sales Invoice", ref.reference_name).as_dict())
	return build(doc.as_dict(), customer, address, invoices)
