"""Which withholding tax goes in which Close Report section. No Frappe, so tests run it alone.

Two accounts, two directions (docs.kiluth.com/finance/tax):
- Withholding Tax Receivable - K: tax a client withheld from Kiluth. A credit
  Kiluth claims back, proved by the client's 50 ทวิ certificate. Section 03.
- Withholding Tax Payable - K: tax Kiluth withheld from its suppliers and owes
  the Revenue Department on ภ.ง.ด.3 / ภ.ง.ด.53. Section 04.

A journal that moves client tax out of Payable into Receivable (Elyscel,
ACC-JV-2026-00133) credits Payable, but it is not tax Kiluth withheld: it
shows in section 03 as moved from earlier months, and never in section 04.
"""

from __future__ import annotations

import re

CLIENT_WHT_ACCOUNT = "Withholding Tax Receivable - K"
KILUTH_WHT_ACCOUNT = "Withholding Tax Payable - K"

_INVOICE = re.compile(r"ACC-SINV-\d{4}-\d{5}(?:-\d+)?")
# A 50 ทวิ scan, by its file name. Any file won't do: Mary Manufacturing's journal
# carries the bank slip of the refund, and invoices carry the invoice PDF.
_CERTIFICATE = re.compile(r"ทวิ|tawi|tavi|certificate|wht[-_ ]?cert", re.I)


def invoices_in(text):
	"""Sales Invoice names written in a journal's remark, in order, once each."""
	return list(dict.fromkeys(_INVOICE.findall(text or "")))


def is_certificate(file_name):
	return bool(_CERTIFICATE.search(file_name or ""))


def split(gl_rows):
	"""GL rows on the two accounts for the month → (client, kiluth).

	A row is a dict with account, voucher_type, voucher_no, party_type, party,
	debit, credit. Returns one dict per voucher:
	- client: voucher_type, voucher_no, party, amt, moved (it came out of Payable)
	- kiluth: voucher_type, voucher_no, party_type, party, amt
	"""
	vouchers = {}
	for r in gl_rows:
		v = vouchers.setdefault((r["voucher_type"], r["voucher_no"]), {"recv": 0.0, "pay": 0.0, "party_type": None, "party": None})
		amt = float(r.get("debit") or 0) - float(r.get("credit") or 0)
		if r["account"] == CLIENT_WHT_ACCOUNT:
			v["recv"] += amt
		elif r["account"] == KILUTH_WHT_ACCOUNT:
			v["pay"] -= amt
		if r.get("party") and not v["party"]:
			v["party_type"], v["party"] = r.get("party_type"), r["party"]

	client, kiluth = [], []
	for (vt, vn), v in vouchers.items():
		recv, pay = round(v["recv"], 2), round(v["pay"], 2)
		if recv > 0:
			client.append({"voucher_type": vt, "voucher_no": vn, "party": v["party"], "amt": recv, "moved": pay > 0})
		elif pay > 0 and recv == 0 and v["party_type"] != "Customer":
			kiluth.append({"voucher_type": vt, "voucher_no": vn, "party_type": v["party_type"], "party": v["party"], "amt": pay})
	return client, kiluth


def by_form(kiluth, supplier_type):
	"""Section 04 totals: ภ.ง.ด.3 (individuals), ภ.ง.ด.53 (companies), and payee type not set.

	`supplier_type(party)` returns the Supplier's type, or None."""
	pnd3 = pnd53 = unknown = 0.0
	for row in kiluth:
		kind = supplier_type(row["party"]) if row["party_type"] == "Supplier" and row["party"] else None
		if kind == "Individual":
			pnd3 += row["amt"]
		elif kind == "Company":
			pnd53 += row["amt"]
		else:
			unknown += row["amt"]
	return pnd3, pnd53, unknown
