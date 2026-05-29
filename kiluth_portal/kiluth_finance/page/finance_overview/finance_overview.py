"""Finance Overview dashboard — live KPI loader.

Reads from the 1-May-2026 Poom-confirmed true-up snapshot and adds live GL
deltas since then to produce current lifetime figures.

The dashboard's 5 KPIs cannot be derived purely from GL because the rekey
journal entry (`ACC-JV-2026-00102`, backdated 2025-12-31) bundled all
pre-2026 net loan position into a single number — the historical split of
"returned to Poom" vs "Poom-paid for Kiluth" is not separately queryable.

So this module anchors on the snapshot Poom confirmed on 1 May 2026 and
adds GL-derived deltas. When the next true-up happens (post-2026-06-05),
update SNAPSHOT_DATE and SNAPSHOT below; the dashboard re-anchors.
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import getdate, nowdate

from kiluth_portal.utils.financial_report import (
	COMPANY,
	LOAN_ACCOUNT,
	_cash_balance_on,
	_loan_balance_on,
	_sum_root,
)

# ─── Snapshot anchor ────────────────────────────────────────────────────────
# Poom-confirmed true-up snapshot. Update both values together when the next
# true-up is posted (typically just after the 5th-of-month financial report
# fires, once Poom-paid expenses for the prior month are entered).

SNAPSHOT_DATE = "2026-05-01"
SNAPSHOT = {
	"revenue": 298376.00,
	"expenses": 743234.50,
	"returned_to_poom": 139180.50,
	"kiluth_paid": 159195.50,
	"loan_balance": 444858.50,
}

# Stretch goal beyond break-even — displayed in the "Interpretation" section.
TARGET_REVENUE = 1_000_000.00


# ─── Helpers ────────────────────────────────────────────────────────────────

def _gl_account_dr_cr(account: str, start, end) -> tuple[float, float]:
	"""Return (sum_debits, sum_credits) for an account in [start, end].

	Needed because `_account_balance_on` returns the net (debits − credits),
	but we want gross debits and credits independently so we can split
	"returned-to-Poom" (debits) from "Poom-paid-for-Kiluth" (credits).
	"""
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(debit), 0) AS d, COALESCE(SUM(credit), 0) AS c
		FROM `tabGL Entry`
		WHERE company = %s AND is_cancelled = 0
			AND account = %s
			AND posting_date BETWEEN %s AND %s
		""",
		(COMPANY, account, start, end),
	)
	return float(row[0][0] or 0), float(row[0][1] or 0)


# ─── Public entry point ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_finance_overview() -> dict:
	"""Lifetime KPIs for the Finance Overview dashboard."""
	if not frappe.has_permission("Server Script", "write"):
		# Same proxy permission as the monthly report — System Manager grants it.
		frappe.throw("Not permitted to view Finance Overview.")

	snapshot_date = getdate(SNAPSHOT_DATE)
	today = getdate(nowdate())
	delta_start = snapshot_date + datetime.timedelta(days=1)

	# If clock is somehow before the snapshot, show snapshot figures with zero
	# deltas. Defensive — shouldn't happen in production.
	if delta_start > today:
		delta_start = today

	# Deltas from GL since snapshot.
	delta_revenue = -_sum_root("Income", delta_start, today)
	delta_expenses = _sum_root("Expense", delta_start, today)
	loan_dr_delta, loan_cr_delta = _gl_account_dr_cr(LOAN_ACCOUNT, delta_start, today)

	# Returned-to-Poom = debits to loan (Kiluth paying Poom back).
	# Kiluth-paid-from-cash = expenses NOT funded by loan = total expenses − loan credits.
	# Mid-period note: kiluth_paid_delta + returned_delta need not equal
	# revenue_delta — the difference is what's sitting in Kiluth's bank
	# awaiting the next true-up.
	delta_returned_to_poom = loan_dr_delta
	delta_kiluth_paid = delta_expenses - loan_cr_delta

	lifetime_revenue = SNAPSHOT["revenue"] + delta_revenue
	lifetime_expenses = SNAPSHOT["expenses"] + delta_expenses
	lifetime_returned = SNAPSHOT["returned_to_poom"] + delta_returned_to_poom
	lifetime_kiluth_paid = SNAPSHOT["kiluth_paid"] + delta_kiluth_paid

	loan_balance = _loan_balance_on(today)
	cash_balance = _cash_balance_on(today)

	days_since = (today - snapshot_date).days

	return {
		"snapshot_date": snapshot_date.isoformat(),
		"as_of": today.isoformat(),
		"days_since_snapshot": days_since,
		# Data Collected
		"money_kiluth_made": lifetime_revenue,
		"total_paid_out": lifetime_expenses,
		"returned_to_poom": lifetime_returned,
		"kiluth_paid_out": lifetime_kiluth_paid,
		"still_owes_poom": loan_balance,
		# Side info
		"cash_in_kiluth": cash_balance,
		# Interpretation
		"next_milestone_target": TARGET_REVENUE,
		"next_milestone_remaining": max(0.0, TARGET_REVENUE - lifetime_revenue),
	}
