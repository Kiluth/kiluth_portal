"""Checks for kiluth_portal/utils/report_email.py. No Frappe, no network:

	python3 kiluth_portal/tests/test_report_email.py
"""

import importlib.util
import os

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "utils", "report_email.py")
spec = importlib.util.spec_from_file_location("report_email", path)
re_ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(re_)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


A = "https://portal.kiluth.com/assets/kiluth_portal/"
P = "https://portal.kiluth.com"

fin = re_.email_html(title="Monthly Financial Report", kicker="September 2026",
	lines=["Hi team,", "Kiluth's financial report for **1–30 September 2026** is attached."],
	hero="hero-financial.jpg", assets=A, portal_url=P, attachment="Kiluth-Financial-Report-2026-09.pdf")
check("financial wording", "Hi team," in fin and "Kiluth&#x27;s financial report for" in fin
	and "1–30 September 2026</span> is attached." in fin and "— Kiluth Portal" in fin)
check("financial hero", A + "email/hero-financial.jpg" in fin)
check("financial attachment", "Kiluth-Financial-Report-2026-09.pdf" in fin)
check("no button without href", "#fefefe" not in fin)
check("no gradients", "gradient" not in fin)
check("link override", "body .email-body a.k" in fin and "@media screen" in fin)
check("portal link", 'href="https://portal.kiluth.com"' in fin and ">portal.kiluth.com<" in fin)
check("mint kicker", "#7ee2a8" in fin and "September 2026" in fin)
check("fonts", A + "certificate/theinhardt-light.woff2" in fin)

url = "https://portal.kiluth.com/app/task/TASK-2026-00029"
close = re_.email_html(title="Close Report", kicker="September 2026",
	lines=["The books for **September 2026** are closed. The Close Report is attached."],
	hero="hero-close.jpg", assets=A, portal_url=P, attachment="Kiluth-Close-Report-2026-09.pdf",
	button="Open the close task", href=url)
check("close wording", "The books for" in close and "are closed. The Close Report is attached." in close)
check("close button", "Open the close task" in close and f'href="{url}"' in close
	and 'bgcolor="#fefefe"' in close and 'class="k"' in close)

bad = re_.email_html(title="<b>x</b>", kicker="k", lines=["a <i>b</i> **<c>**"], hero="h.jpg",
	assets=A, portal_url=P)
check("escapes", "<b>x</b>" not in bad and "&lt;i&gt;" in bad and "&lt;c&gt;" in bad and "<i>" not in bad)
check("no attachment row", "Attached" not in bad)

print("FAIL: " + ", ".join(fails) if fails else "OK")
raise SystemExit(1 if fails else 0)
