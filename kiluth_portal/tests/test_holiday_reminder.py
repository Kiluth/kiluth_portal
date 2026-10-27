"""Checks for kiluth_portal/kiluth_hr/holiday_reminder.py wording. No Frappe needed:

	python3 kiluth_portal/tests/test_holiday_reminder.py
"""

import datetime as dt
import importlib.util
import os

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("holiday_reminder", os.path.join(here, "..", "kiluth_hr", "holiday_reminder.py"))
hr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hr)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


mon, sun = dt.date(2026, 10, 19), dt.date(2026, 10, 25)
one = hr.wording("Phuttipan", [(dt.date(2026, 10, 23), "HM King Chulalongkorn Memorial Day")], mon, sun)
check("one subject", one["subject"] == "Day off on Friday 23 October: HM King Chulalongkorn Memorial Day")
check("one title", one["title"] == "A day off this week")
check("week label", one["kicker"] == "19–25 October 2026")
check("greeting", one["lines"][0] == "Hi Phuttipan,")
check("day line", one["lines"][1] == "**Friday 23 October**: HM King Chulalongkorn Memorial Day.")

two = hr.wording("", [(dt.date(2026, 12, 31), "New Year's Eve"), (dt.date(2027, 1, 1), "New Year's Day")],
	dt.date(2026, 12, 28), dt.date(2027, 1, 3))
check("two subject", two["subject"] == "2 days off this week")
check("no name", two["lines"][0] == "Hi,")
check("across months", two["kicker"] == "28 December – 3 January 2027")

print("all checks passed" if not fails else "FAILED: " + ", ".join(fails))
raise SystemExit(1 if fails else 0)
