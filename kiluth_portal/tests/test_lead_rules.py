"""Checks for kiluth_portal/utils/lead_rules.py. No Frappe needed:

	python3 kiluth_portal/tests/test_lead_rules.py
"""

import importlib.util
import os
import sys
from datetime import date, datetime

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "utils", "lead_rules.py")
spec = importlib.util.spec_from_file_location("lead_rules", path)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


t = datetime
# Who gets the next lead
check("nobody in Sales gives None", r.least_loaded([]) is None)
check("fewest open wins", r.least_loaded([("a", 3, t(2026, 10, 1)), ("b", 1, t(2026, 10, 20))]) == "b")
check("tie: longest ago wins", r.least_loaded([("a", 1, t(2026, 10, 20)), ("b", 1, t(2026, 10, 2))]) == "b")
check("tie: never given one wins", r.least_loaded([("a", 0, t(2026, 10, 2)), ("b", 0, None)]) == "b")
check("full tie: by name", r.least_loaded([("b", 0, None), ("a", 0, None)]) == "a")

# One working day (Oct 2026: Fri 23 is Chulalongkorn Day, a holiday)
hol = {date(2026, 10, 23)}
check("weekday to next day", r.one_working_day_after(t(2026, 10, 20, 15, 0), hol) == t(2026, 10, 21, 15, 0))
check("skips the holiday", r.one_working_day_after(t(2026, 10, 22, 9, 30), hol) == t(2026, 10, 26, 9, 30))
check("Friday to Monday", r.one_working_day_after(t(2026, 10, 16, 17, 0), set()) == t(2026, 10, 19, 17, 0))
check("Saturday to Monday", r.one_working_day_after(t(2026, 10, 24, 10, 0), set()) == t(2026, 10, 26, 10, 0))
check("Sunday to Monday", r.one_working_day_after(t(2026, 10, 25, 22, 0), set()) == t(2026, 10, 26, 22, 0))

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
