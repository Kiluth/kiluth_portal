"""Checks for kiluth_portal/kiluth_hr/learning_report.py. No Frappe needed:

	python3 kiluth_portal/tests/test_learning_report.py
"""

import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "kiluth_hr", "learning_report.py")
spec = importlib.util.spec_from_file_location("learning_report", path)
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


RECORD = """Result: **8/10 — pass**

| # | Question | Answer | Right? | Source |
| --- | --- | --- | --- | --- |
| 1 | Who signs? | A | ✓ | Estimation — Who signs |
| 2 | When? | B | ✗ | Estimation — Who signs |
| 3 | Flawed question, replaced | C | — | Bug Reports |
"""
PAGES = [("Estimation", "delivery/estimation", ["Who signs", "The rules"]),
	("Bug Reports", "technology/bug-reports", ["How to report"])]

score, rows = lr.parse_record(RECORD)
check("score", score == "8/10 — pass")
check("rows", len(rows) == 3 and rows[0]["right"] and not rows[1]["right"] and not rows[2]["counted"])
check("resolve page and heading", lr.resolve("Estimation — Who signs", PAGES) == ("Estimation", "delivery/estimation", "Who signs"))
check("resolve drops step numbers", lr.resolve("Bug Reports — step 3", PAGES)[0] == "Bug Reports")
check("resolve heading only", lr.resolve("How to report", PAGES)[1] == "technology/bug-reports")
check("resolve unknown", lr.resolve("Nothing like it", PAGES) is None)


def cert(name, email, status, created, expiry=None, record=RECORD):
	return {"name": name, "title": f"Sales – {email}", "status": status, "effective_date": None,
		"expiry_date": expiry, "creation": created, "record": record}


A, B, C = "a@kiluth.com", "b@kiluth.com", "c@kiluth.com"
certs = [
	cert("DOC-1", A, "Signed", "2026-10-03 10:00:00", "2027-10-03"),
	cert("DOC-2", B, "Void", "2026-10-04 10:00:00"),
	cert("DOC-3", C, "Signed", "2025-12-01 10:00:00", "2026-12-01"),  # expires within two months of Oct
	cert("DOC-4", "d@kiluth.com", "Signed", "2025-11-01 10:00:00", "2027-11-01"),  # quiet: nothing to act on
]
findings = lr.group_findings([
	{"name": "TASK-1", "subject": "Ship it", "hygiene": "Fail", "owner": "e@kiluth.com", "status": "Completed",
		"modified": "2026-10-20 10:00:00", "hygiene_note": "completed by e@kiluth.com, who did the work — only the requester (a@kiluth.com) completes"},
	{"name": "TASK-2", "subject": "Next month", "hygiene": "Fail", "owner": A, "status": "Open",
		"modified": "2026-11-02 10:00:00", "hygiene_note": "no done when"},
], *lr.month_bounds("2026-10"))
check("finding goes to whoever completed", list(findings) == ["e@kiluth.com"])

a = lr.analyse("2026-10", certs, findings, PAGES)
views = {e: lr.person_view(e, p, a) for e, p in a["people"].items()}
act = {e for e, p in a["people"].items() if lr.has_action(p, views[e])}
check("emails attempt, expiry and task people only", act == {A, B, C, "e@kiluth.com"})
check("summary due when someone tested", lr.summary_due(a))
quiet = lr.analyse("2026-09", certs[:1], {}, PAGES)
check("summary skipped in a quiet month", not lr.summary_due(quiet))

reports = {e: lr.person_html(e, a["people"][e], views[e], a) for e in act}
check("requester hidden in task notes", A not in reports["e@kiluth.com"] and "a teammate" in reports["e@kiluth.com"])
check("checks pass", lr.check_reports(a, reports, lr.summary_html(a), {}) == [])
leaky = dict(reports, **{A: reports[A] + B})
check("other email caught", lr.check_reports(a, leaky, None, {}) == [f"{A}'s report names {B}"])
check("full name caught in summary",
	lr.check_reports(a, {}, lr.summary_html(a) + "Bee Person", {B: "Bee Person"}) == [f"the company summary names {B}"])
check("one-word names ignored", lr.check_reports(a, {}, lr.summary_html(a) + " Bee ", {B: "Bee"}) == [])
check("docs to check: one section missed twice", [x[0] for x in lr.docs_to_check(a)] == ["Estimation"])
check("summary hides doc detail below the minimum group", "Fewer than 3 people" in lr.summary_html(a)
	and "Times missed" not in lr.summary_html(a))
check("step kept when no heading", lr.resolve("Bug Reports — step 3", PAGES)[2] == "Step 3")
STEPS = [("Retiring a Hosting Resource", "technology/retiring", ["Steps", "4. Clean up", "5. Destroy the VM"])]
check("step uses the page's own step heading", lr.resolve("Retiring — step 5", STEPS)[2] == "5. Destroy the VM")
check("step range kept", lr.resolve("Retiring a Hosting Resource — Steps 2–3", STEPS)[2] == "Steps 2–3")
check("small group: one company total, no per-course rows", "All courses" in lr.summary_html(a)
	and not __import__("re").search(r">Sales</td><td>\d+ / ", lr.summary_html(a)))
check("page with no section is Other", lr.resolve("Bug Reports", PAGES)[2] is None
	and lr.sections_cell(__import__("collections").Counter({"": 2})) == "Other ×2")
check("placeholder gone", "a step or rule" not in lr.summary_html(a) + "".join(reports.values()))
check("counted score made plain", lr.plain_score("8/10 counted — not yet.") == "8/10* — not yet.")
check("attempts show a date, not a certificate number", "DOC-2" not in reports[B] and "2026-10-04" in reports[B])

FLAWED = RECORD.replace("Flawed question, replaced", "(flawed, replaced) A feature is Optimistic 6, Likely 9, Pessimistic 18 hours. What are its PERT and its σ?")
D, E = "d2@kiluth.com", "e2@kiluth.com"
big = lr.analyse("2026-10", certs + [cert("DOC-5", D, "Void", "2026-10-05 10:00:00", record=FLAWED),
	cert("DOC-6", E, "Void", "2026-10-06 10:00:00", record=FLAWED)], {}, PAGES)
s = lr.summary_html(big)
check("full flawed question, once, no prefix", s.count("What are its PERT and its σ?") == 1 and "(flawed" not in s)
check("big group: per course again", "All courses" not in s)
check("one docs table, checked docs marked", "Docs to check" not in s and "Times missed" in s and "Check</span>" in s)

rp = lr._rp()
check("each line break is a line", rp._row_height(["x", "a<br>b<br>c<br>d"], rp.GRID[2]) > rp._row_height(["x", "a b c d"], rp.GRID[2]) * 2)

check("heading parser", lr._heading_texts('<h2 id="x">Who&#x27;s in<a role="anchor" href="#x"></a></h2><h3>Table</h3>') == ["Who's in"])

mail = lr.email_html(False, "October 2026", "https://portal.kiluth.com/assets/kiluth_portal/")
check("person email wording", "Your learning report for October 2026 is attached." in mail
	and "It's yours: it isn't a score, and other people see it only if you share it." in mail and "— Kiluth" in mail)
check("summary email wording", "The company learning summary for October 2026 is attached.<br>No names."
	in lr.email_html(True, "October 2026", "https://x/"))
check("email design rules", "gradient" not in mail and "#fefefe" in mail and 'class="k"' in mail
	and "learning/hero-person.jpg" in mail)
for jpg in ("hero-person.jpg", "hero-summary.jpg"):
	check(f"photo {jpg} shipped", os.path.exists(os.path.join(here, "..", "public", "learning", jpg)))

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
