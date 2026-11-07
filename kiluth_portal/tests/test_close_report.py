"""Checks for the Close Report's withholding sections and its fonts. No Frappe, no network:

	python3 kiluth_portal/tests/test_close_report.py

October 2026 case (TASK-2026-00106): Mary Manufacturing withheld ฿1,455.72
(ACC-JV-2026-00132) and ฿6,063 of Elyscel's tax moved from Payable to
Receivable (ACC-JV-2026-00133). Both are tax clients withheld; neither is
tax Kiluth withheld.
"""

import os
import re
import sys
import types

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))


class _dict(dict):
	__getattr__ = dict.get


# Stand-ins so close_report imports without a site.
frappe = types.ModuleType("frappe")
frappe._dict = _dict
frappe.whitelist = lambda *a, **k: (lambda f: f)
sys.modules["frappe"] = frappe
fr = types.ModuleType("kiluth_portal.utils.financial_report")
fr.COMPANY = "Kiluth"
fr._cash_balance_on = lambda d: 0
fr._fmt = lambda a: "" if a is None else ("—" if abs(a) < 0.005 else (f"(฿ {-a:,.2f})" if a < 0 else f"฿ {a:,.2f}"))
sys.modules["kiluth_portal.utils.financial_report"] = fr

from kiluth_portal.utils import close_report as cr  # noqa: E402
from kiluth_portal.utils import close_wht as cw  # noqa: E402
from kiluth_portal.utils import report_pdf as rp  # noqa: E402

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


R, P = cw.CLIENT_WHT_ACCOUNT, cw.KILUTH_WHT_ACCOUNT


def gl(account, vt, vn, debit=0, credit=0, party_type=None, party=None):
	return {"account": account, "voucher_type": vt, "voucher_no": vn, "party_type": party_type, "party": party,
		"debit": debit, "credit": credit}


# ─── October 2026 ────────────────────────────────────────────────────────────

october = [
	gl(R, "Journal Entry", "ACC-JV-2026-00132", debit=1455.72),
	gl(R, "Journal Entry", "ACC-JV-2026-00133", debit=6063),
	gl(P, "Journal Entry", "ACC-JV-2026-00133", credit=6063),
]
client, kiluth = cw.split(october)
by_no = {r["voucher_no"]: r for r in client}
check("oct: both client items", sorted(by_no) == ["ACC-JV-2026-00132", "ACC-JV-2026-00133"])
check("oct: Mary amount", by_no["ACC-JV-2026-00132"]["amt"] == 1455.72 and not by_no["ACC-JV-2026-00132"]["moved"])
check("oct: Elyscel moved", by_no["ACC-JV-2026-00133"]["amt"] == 6063 and by_no["ACC-JV-2026-00133"]["moved"])
check("oct: client total", round(sum(r["amt"] for r in client), 2) == 7518.72)
check("oct: nothing Kiluth withheld", kiluth == [])
check("oct: forms empty", cw.by_form(kiluth, lambda p: None) == (0.0, 0.0, 0.0))

check("invoices in remark", cw.invoices_in("for invoice ACC-SINV-2026-00222-1. They paid") == ["ACC-SINV-2026-00222-1"])
check("invoices once each, in order", cw.invoices_in(
	"ACC-SINV-2026-00210 2,220; 00220 1,665; ACC-SINV-2026-00218 513 ACC-SINV-2026-00210") == ["ACC-SINV-2026-00210", "ACC-SINV-2026-00218"])

check("bank slip is no certificate", not cw.is_certificate("2026-10-26-kbiz-wht-refund-mary-manufacturing.jpg"))
check("invoice pdf is no certificate", not cw.is_certificate("ACC-SINV-2026-00021.pdf"))
check("certificates by name", all(cw.is_certificate(n) for n in
	["50 ทวิ Mary.pdf", "50ทวิ-elyscel-00210.jpg", "elyscel-50-tawi.pdf", "WHT-cert-oct.pdf", "Withholding certificate.png"]))

# ─── Tax Kiluth withheld from suppliers ──────────────────────────────────────

month = [
	gl(P, "Payment Entry", "PE-1", credit=300, party_type="Supplier", party="Jane"),
	gl(P, "Payment Entry", "PE-2", credit=900, party_type="Supplier", party="Acme Co"),
	gl(P, "Journal Entry", "JV-9", credit=50),
	gl(P, "Journal Entry", "JV-10", debit=120, credit=120),  # moved and moved back: nets to nothing
	gl(P, "Journal Entry", "JV-11", credit=200, party_type="Customer", party="Elyscel"),  # client tax, wrong account
	gl(R, "Payment Entry", "PE-3", debit=600, party_type="Customer", party="Mary"),
	gl(R, "Journal Entry", "JV-12", credit=400),  # credit used up: not withheld this month
]
client, kiluth = cw.split(month)
check("supplier rows only", sorted(r["voucher_no"] for r in kiluth) == ["JV-9", "PE-1", "PE-2"])
check("payment-entry client", [(r["voucher_no"], r["party"], r["moved"]) for r in client] == [("PE-3", "Mary", False)])
kinds = {"Jane": "Individual", "Acme Co": "Company"}
check("forms", cw.by_form(kiluth, kinds.get) == (300.0, 900.0, 50.0))

# ─── The report page ─────────────────────────────────────────────────────────

period = cr._period_from_subject("Close the books for October 2026")
task = _dict(name="TASK-2026-00087")
data = {
	"booked": [_dict(voucher_type="Journal Entry", n=10)], "cash": 147403.09, "bank": 147403.09,
	"client_wht": [
		{"voucher_type": "Journal Entry", "voucher_no": "ACC-JV-2026-00132", "party": "Mary Manufacturing Co., Ltd.",
			"amt": 1455.72, "moved": False, "certificate": False},
		{"voucher_type": "Journal Entry", "voucher_no": "ACC-JV-2026-00133", "party": "Elyscel",
			"amt": 6063.0, "moved": True, "certificate": False},
	],
	"pnd3": 0.0, "pnd53": 0.0, "wht_unknown": 0.0, "slips": _dict(n=0), "salary_tax": 0.0, "social_security": 0.0,
}
html = cr._render_html(period, data, task)
s03 = html.split("Tax clients withheld")[1].split("Tax Kiluth withheld")[0]
s04 = html.split("Tax Kiluth withheld")[1].split("Salaries")[0]
check("03: Mary", "Mary Manufacturing Co., Ltd." in s03 and "฿ 1,455.72" in s03)
check("03: Elyscel moved", "Elyscel" in s03 and "฿ 6,063.00" in s03 and "moved from earlier months" in s03)
check("03: total", "฿ 7,518.72" in s03 and "No client withheld tax" not in s03)
check("03: certificates missing", s03.count("no certificate") == 2)
check("04: no 6,063", "6,063" not in s04 and "Payee type not set" not in s04 and s04.count("Nothing to file") == 2)
check("thai in its font", "<span class='th'>ภ.ง.ด.3</span>" in s04 and "<span class='th'>ภ.ง.ด.53</span>" in s04
	and "<span class='th'>ทวิ</span>" in s03)

# ─── Fonts ───────────────────────────────────────────────────────────────────

faces = rp.font_faces()
check("fonts inline, no URL", faces.count("base64,") == 4 and "/files/" not in faces and "http" not in faces)
check("thai font", "font-family: 'IBM Plex Sans Thai'" in faces and "font-family: 'Theinhardt'" in faces)
check("thai font class", ".th { font-family: 'IBM Plex Sans Thai'" in rp.CSS)
check("fonts token in page", rp.FONTS_TOKEN in html)
# Frappe's scrub_urls (frappe/utils/data.py URL_NOTATION_PATTERN) breaks any font it matches.
frappe_url = re.compile(r'(:[\s]?url)(\([\'"]?)((?!http)[^\'" >]+)([\'"]?\))')
check("frappe leaves the fonts alone", not frappe_url.search(faces))
check("oct: fits the cover page", "Confidential · 1 / 1" in html)

out = os.environ.get("CLOSE_REPORT_HTML")
if out:
	with open(out, "w") as f:
		f.write(html.replace(rp.FONTS_TOKEN, faces))

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
