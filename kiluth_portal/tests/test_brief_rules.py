"""Checks for kiluth_portal/utils/brief_rules.py. No Frappe needed:

	python3 kiluth_portal/tests/test_brief_rules.py

Writes the brief's HTML to /tmp/brief-test.html for a look in a browser.
"""

import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))


def load(name, rel):
	spec = importlib.util.spec_from_file_location(name, os.path.join(here, "..", rel))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


br = load("brief_rules", "utils/brief_rules.py")
rp = load("report_pdf", "utils/report_pdf.py")

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


def raises(fn):
	try:
		fn()
	except ValueError:
		return True
	return False


SUMMARY = [
	["โปรเจกต์", [["ลูกค้า", ["Baanploypoom"]], ["ผู้ติดต่อจาก Kiluth", ["Reaw"]], ["ระบบหรือช่องทางที่มีในปัจจุบัน", []]]],
	["เป้าหมาย", [["ผลลัพธ์ที่ต้องการ", ["เพิ่มยอดการจองหรือการนัดเยี่ยมชม", "<script>alert(1)</script>"]]]],
	["Scope", [["What it is", ["Website"]]]],
]

# Shape checks
check("good summary passes", len(br.clean_summary(SUMMARY)) == 3)
check("not a list fails", raises(lambda: br.clean_summary({"a": 1})))
check("empty fails", raises(lambda: br.clean_summary([])))
check("bad section fails", raises(lambda: br.clean_summary([["x"]])))
check("bad line fails", raises(lambda: br.clean_summary([["x", [["y", "not a list"]]]])))
cut = br.clean_summary([["s", [["l", ["a" * 900, 5, "", "  ok  "]]]]])
check("long answer cut to 500", len(cut[0][1][0][1][0]) == 500)
check("non-text and blank answers dropped", cut[0][1][0][1][1:] == ["ok"])
check("sections capped", len(br.clean_summary([["s", []]] * 30)) == br.LIMITS["sections"])
check("data must be an object", raises(lambda: br.clean_data([1])))
check("data size capped", raises(lambda: br.clean_data({"x": "y" * 70000})))
check("data passes", br.clean_data({"client": "Baanploypoom"}) == {"client": "Baanploypoom"})

# Names
check("file base", br.file_base("PROJ-0015", "2026-10-28", False) == "client-brief-PROJ-0015-2026-10-28")
check("test file base", br.file_base("PROJ-0015", "2026-10-28", True).startswith("TEST-"))
check("odd date not in the name", br.file_base("PROJ-0015", "../x", False).endswith("-undated"))
check("project pattern", br.PROJECT_RE.match("PROJ-0015") and not br.PROJECT_RE.match("PROJ-15"))

# The PDF's HTML
meta = {"project": "PROJ-0015", "lang": "th", "test": True, "client": "Baanploypoom", "by": "Reaw", "date": "2026-10-28"}
html = br.build_html(br.clean_summary(SUMMARY), meta, rp)
check("answers escaped", "<script>" not in html and "&lt;script&gt;" in html)
check("thai in its font span", "<span class='th'" in html)
check("thai label on cover", "บรีฟโปรเจกต์" in html and "ทดสอบจาก staging" in html)
check("empty answer says so", "ยังไม่ระบุ" in html)
check("sections numbered", "<span class='n'>03</span>" in html)
check("report design used", "class='page" in html and "Kiluth LTD." in html)
en = br.build_html(br.clean_summary(SUMMARY), {**meta, "lang": "en", "test": False}, rp)
check("english words", "Client brief" in en and "Not given" in en and "staging" not in en)

with open("/tmp/brief-test.html", "w") as f:
	f.write(html.replace(rp.FONTS_TOKEN, rp.font_faces("https://portal.kiluth.com")))

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
