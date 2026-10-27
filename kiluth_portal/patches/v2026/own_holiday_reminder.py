"""Turn off HRMS's holiday reminder: kiluth_hr/holiday_reminder.py sends it now,
in the Kiluth design (Poom, 2026-10-27). Without this, people get both."""

import frappe


def execute():
	frappe.db.set_single_value("HR Settings", "send_holiday_reminders", 0)
