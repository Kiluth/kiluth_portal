"""Checks for kiluth_portal/utils/vat_rules.py. No Frappe needed:

	python3 kiluth_portal/tests/test_vat_rules.py
"""

import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "utils", "vat_rules.py")
spec = importlib.util.spec_from_file_location("vat_rules", path)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


vat = ["VAT - K"]
wht = {"account_head": "Withholding Tax Payable - K", "rate": -3}
row = {"account_head": "VAT - K", "rate": 7}
check("a VAT row", r.vat_rows([row], vat) == [row])
check("withholding stays allowed", r.vat_rows([wht], vat) == [])
check("only the VAT row of two", r.vat_rows([wht, row], vat) == [row])
check("no taxes", r.vat_rows([], vat) == [] and r.vat_rows(None, vat) == [])
check("no VAT account in the chart", r.vat_rows([row], []) == [] and r.vat_rows([row], None) == [])
check("another company's VAT ledger", r.vat_rows([{"account_head": "VAT - X"}], ["VAT - K", "VAT - X"]) != [])
check("a blank row", r.vat_rows([{"account_head": None}], vat) == [])
check("a name that only contains VAT", r.vat_rows([{"account_head": "VAT Refund - K"}], vat) == [])

check("a draft being saved", r.needs_check(0, "save"))
check("a draft with no action", r.needs_check(0, None))
check("a draft being submitted", r.needs_check(1, "submit"))
check("update after submit", not r.needs_check(1, "update_after_submit"))
check("a submitted document", not r.needs_check(1, None))
check("cancel", not r.needs_check(2, "cancel") and not r.needs_check(2, None))

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
