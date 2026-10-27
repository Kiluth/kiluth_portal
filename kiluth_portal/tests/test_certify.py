"""Checks for kiluth_portal/kiluth_hr/certify.py. No Frappe, no network:

	python3 kiluth_portal/tests/test_certify.py
"""

import importlib.util
import os

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "kiluth_hr", "certify.py")
spec = importlib.util.spec_from_file_location("certify", path)
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


ANCHOR = '<a role="anchor" href="#x"><svg><path d="M1"></path></svg></a>'
CERT_PAGE = f"""<html><body><nav>menu</nav><article><h1 id="c">Certification{ANCHOR}</h1>
<h2 id="courses">Courses{ANCHOR}</h2>
<table><thead><tr><th>Course</th><th>For</th><th>Docs the test draws from</th><th>You must be able to</th></tr></thead>
<tbody><tr><td><strong>Design</strong></td><td>Designers</td>
<td><a href="../../creative/ux-workflow">UX Workflow</a>, <a href="../../marketing/brand-and-pr">Brand and PR</a></td>
<td>Link sign-off proof · show client work only with written OK</td></tr></tbody></table>
<h2 id="check">Kiluth’s check{ANCHOR}</h2><p>Every pass is checked.</p></article></body></html>"""
UX = f"""<article><h1>UX Workflow{ANCHOR}</h1><p>Intro <strong>bold</strong>.</p>
<h2 id="t">3. Explore designs{ANCHOR}</h2><ul><li>Iterate</li></ul>
<h2 id="u">4. Test and hand over{ANCHOR}</h2><table><tr><th>Right</th><th>Wrong</th></tr><tr><td>Fix it</td><td>Leave it</td></tr></table></article>"""
BRAND = f"""<article><h1>Brand and PR{ANCHOR}</h1><h2>Showing client work{ANCHOR}</h2><p>Written OK only.</p></article>"""
FETCH = {"creative/ux-workflow": UX, "marketing/brand-and-pr": BRAND, "hr/certification": CERT_PAGE}


def record(rows, result="10/10 — pass.", repeats=False, options=None):
	head = "| # | Question | Answer given | Correct answer | Right? | Source |" + (" Repeats |" if repeats else "")
	lines = [head, "| --- " * (7 if repeats else 6) + "|"]
	for r in rows:
		lines.append("| " + " | ".join(r) + " |")
	opts = options or [f"{r[0]}. **A) yes** · B) no · C) maybe" for r in rows if r[4] in ("✓", "✗")]
	return f"# Design test\n\nResult: **{result}**\n\n" + "\n".join(lines) + "\n\n## Options\n\n" + "\n".join(opts) + "\n"


GOOD = [(str(i), f"Q{i}?", "A", "A", "✓", "UX Workflow — 3. Explore designs") for i in range(1, 10)] + [
	("10", "Q10?", "A", "A", "✓", "Brand and PR — Showing client work")]

# Parsing
rec = cf.parse_record(record(GOOD))
check("parse passed", rec["passed"] and len(rec["rows"]) == 10)
check("parse options", rec["options"]["1"] == [("A", "yes", True), ("B", "no", False), ("C", "maybe", False)])
check("not yet is not a pass", not cf.parse_record(record(GOOD, "9/10 — not yet."))["passed"])
flawed = GOOD[:5] + [("6", "(flawed) Q6", "C", "A", "not counted", "UX Workflow — 3. Explore designs"),
	("6R", "(replacement) Q6R", "A", "A", "✓", "UX Workflow — 3. Explore designs")] + GOOD[6:]
r2 = cf.parse_record(record(flawed))
check("flawed row not counted", [r["id"] for r in r2["rows"] if r["counted"]] == ["1", "2", "3", "4", "5", "6R", "7", "8", "9", "10"])
check("6R options parsed", "6R" in r2["options"])

# Docs
title, heads, text = cf.page_from_html(UX)
check("page title", title == "UX Workflow")
check("headings without anchors", heads == ["3. Explore designs", "4. Test and hand over"])
check("table kept", "| Right | Wrong |" in text and "| Fix it | Leave it |" in text)
check("list kept", "- Iterate" in text)
courses = cf.course_rows(CERT_PAGE)
check("course row", courses["Design"]["docs"] == [("UX Workflow", "creative/ux-workflow"), ("Brand and PR", "marketing/brand-and-pr")])
check("course must", courses["Design"]["must"].startswith("Link sign-off proof"))
pages = {s: cf.page_from_html(FETCH[s]) for _, s in courses["Design"]["docs"]}

# Code checks
check("good record passes code", cf.code_checks(rec, courses["Design"], pages, set()) == [])
check("flawed + replaced passes code", cf.code_checks(r2, courses["Design"], pages, set()) == [])
dropped = cf.parse_record(record(GOOD[:9], "9/9 — pass."))
check("dropped question fails", any("not 10" in w for _, _, w in cf.code_checks(dropped, courses["Design"], pages, set())))
bad_src = cf.parse_record(record(GOOD[:9] + [("10", "Q", "A", "A", "✓", "Brand and PR §2")]))
check("source format", any(c == "source" and q == "10" for c, q, _ in cf.code_checks(bad_src, courses["Design"], pages, set())))
other = cf.parse_record(record(GOOD[:9] + [("10", "Q", "A", "A", "✓", "Sales Playbook — Who may sell")]))
check("page outside course", any("isn't one of this course" in w for _, _, w in cf.code_checks(other, courses["Design"], pages, set())))
gone = cf.parse_record(record(GOOD[:9] + [("10", "Q", "A", "A", "✓", "Brand and PR — Old heading")]))
check("heading gone", any("no heading" in w for _, _, w in cf.code_checks(gone, courses["Design"], pages, set())))
no_opts = cf.parse_record(record(GOOD, options=["1. A) a · B) b"]))
check("options missing", any("options" in w for _, _, w in cf.code_checks(no_opts, courses["Design"], pages, set())))
two_bold = cf.parse_record(record(GOOD, options=[f"{i}. **A) a** · **B) b** · C) c" for i in range(1, 11)]))
check("two right options", any("exactly one" in w for _, _, w in cf.code_checks(two_bold, courses["Design"], pages, set())))
mism = cf.parse_record(record(GOOD[:9] + [("10", "Q", "B", "B", "✓", "Brand and PR — Showing client work")]))
check("table vs options", any("differ" in w for _, _, w in cf.code_checks(mism, courses["Design"], pages, set())))
rep = cf.parse_record(record([r + ("CERT-00009 Q1",) for r in GOOD], repeats=True))
check("named repeat must be earlier", any(c == "repeat" for c, _, _ in cf.code_checks(rep, courses["Design"], pages, set())))
check("named repeat ok", cf.code_checks(rep, courses["Design"], pages, {"CERT-00009"}) == [])
check("void reason ends with retake", cf.reason_from_code([("source", "3", "x")]).endswith(cf.RETAKE))

# Verdict validation
def verdict(v="sign", **over):
	qs = [{"id": r["id"], "answer_holds": True, "only_one_allowed": True, "tests_a_decision": True,
		"unnamed_repeat_of": "", "note": ""} for r in rec["rows"]]
	for qid, k, val in over.get("q", []):
		next(q for q in qs if q["id"] == qid)[k] = val
	return {"questions": qs, "replacement_fair": over.get("fair", True), "verdict": v,
		"reason_for_person": over.get("reason", "")}

check("sign ok", cf.validate_verdict(verdict(), rec)[0] == "sign")
check("void ok", cf.validate_verdict(verdict("void", q=[("3", "only_one_allowed", False)], reason="Q3 has two answers."), rec)[0] == "void")
for name, v in [("sign despite failed question", verdict(q=[("3", "answer_holds", False)])),
		("sign despite unnamed repeat", verdict(q=[("2", "unnamed_repeat_of", "CERT-00001 Q1")])),
		("void with nothing failed", verdict("void", reason="x")),
		("void without reason", verdict("void", q=[("3", "answer_holds", False)])),
		("missing question", dict(verdict(), questions=verdict()["questions"][:9])),
		("bad verdict", dict(verdict(), verdict="maybe")),
		("not a bool", verdict(q=[("1", "answer_holds", "yes")]))]:
	try:
		cf.validate_verdict(v, rec)
		fails.append("should raise: " + name)
	except ValueError:
		pass

# The whole check, model stubbed
calls = []


def ask_ok(system, user):
	calls.append(user)
	return verdict(), {"inputTokens": 1, "outputTokens": 1}


out = cf.evaluate("CERT-00099", "Design – a@kiluth.com", record(GOOD), [], CERT_PAGE, FETCH.get, ask_ok)
check("evaluate signs via model", out["verdict"] == "sign" and out["by"] == "model")
check("prompt has docs, record and certification page", "| Fix it | Leave it |" in calls[0] and "Q10?" in calls[0] and "Every pass is checked." in calls[0])
check("prompt filled", "{{" not in calls[0])
out = cf.evaluate("CERT-00099", "Design – a@kiluth.com", record(GOOD[:9], "9/9 — pass."), [], CERT_PAGE, FETCH.get, ask_ok)
check("code voids without the model", out["verdict"] == "void" and out["by"] == "code" and len(calls) == 1)
out = cf.evaluate("CERT-00099", "Cooking – a@kiluth.com", record(GOOD), [], CERT_PAGE, FETCH.get, ask_ok)
check("unknown course voids", out["verdict"] == "void" and len(calls) == 1)
try:
	cf.evaluate("CERT-00099", "Design – a@kiluth.com", record(GOOD), [], CERT_PAGE, FETCH.get, lambda s, u: ({"verdict": "sign"}, {}))
	fails.append("malformed model answer should raise")
except ValueError:
	pass

# Certificate HTML
page = cf.certificate_html("Design", "Poom <P>", "17 October 2026", "17 October 2027", "CERT-00035")
check("certificate filled", "{{" not in page and "Poom &lt;P&gt;" in page and "CERT-00035" in page)
check("long date", cf.long_date("2026-10-07") == "7 October 2026")
photo = cf.photo_uri()
check("certificate photo", photo.startswith("data:image/jpeg;base64,") and photo[23:] in cf.certificate_html(
	"Design", "P", "a", "b", "c", photo=photo))

# The person's email
A = "https://portal.kiluth.com/assets/kiluth_portal/certificate/"
ok = cf.email_html(True, "Design", "Poom", A, "https://portal.kiluth.com/app/document/CERT-00035",
	cert_id="CERT-00035", expires="17 October 2027")
check("signed email", "Certified" in ok and "CERT-00035" in ok and "17 October 2027" in ok
	and "Every answer right, Poom." in ok and A + "hero-signed.jpg" in ok and "#fefefe" in ok)
no = cf.email_html(False, "Design", "Poom", A, "x", reason="Question 3 <b>is</b> wrong.")
check("not-signed email", "Not signed" in no and "Question 3 &lt;b&gt;is&lt;/b&gt; wrong." in no
	and "hr/certification#the-test" in no and "Certified" not in no)

print("FAIL: " + ", ".join(fails) if fails else "OK")
raise SystemExit(1 if fails else 0)
