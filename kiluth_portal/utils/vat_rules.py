"""Which tax rows charge VAT, kept free of Frappe so it can be tested on its own
(python3 kiluth_portal/tests/test_vat_rules.py).

Why: Kiluth isn't VAT-registered. No tax template adds VAT, but people typed a
"VAT - K" row or duplicated an old document that had one, and 7 paid invoices
charged VAT that way (Poom, 2026-11-05).

A VAT account is a ledger (not a group) named "VAT", as "VAT - K" is under
Duties and Taxes. Withholding Tax Payable / Receivable are other accounts and
stay allowed. When Kiluth registers for VAT (utils/tax_checks.py watches the
line), remove the hook.

The Frappe side (refusing the save or submit) is in vat.py.
"""

from __future__ import annotations

# The account_name of a VAT ledger. Its name adds the company abbreviation: "VAT - K".
VAT_ACCOUNT_NAME = "VAT"


def vat_rows(taxes, vat_accounts) -> list:
	"""The rows of `taxes` whose account_head is one of `vat_accounts`, in order."""
	vat = set(vat_accounts or ())
	return [row for row in taxes or () if row.get("account_head") in vat]


def needs_check(docstatus, action) -> bool:
	"""Whether a validate is a draft being saved or submitted.

	Frappe runs validate on save (docstatus 0) and on submit (docstatus 1, action
	"submit"), not on cancel, update after submit or print. Anything else calling it
	on a submitted or cancelled document is about an old document: leave it be.
	An amended copy of a cancelled document is a new draft, so it is checked.
	"""
	return docstatus == 0 or action == "submit"
