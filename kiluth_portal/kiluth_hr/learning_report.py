"""Monthly learning reports — implements docs.kiluth.com/hr/learning-report.

Runs on the 6th at 09:00 (Asia/Bangkok), for the month before, with an hourly
catch-up like the financial report. Reads every Certificate Document with its
attached test record, and the task checker's verdicts (Task.hygiene), then:

- emails each person their own private PDF, but only when there is something
  to act on: an attempt that month, a certificate expiring within two months,
  or a task-habit finding
- emails management@kiluth.com a company summary with no names, but only when
  someone took a test that month
- opens one Task per department on PROJ-0001 listing its docs to check

Ported from the HR builder script (departments/hr/artifacts/learning-report/
build.py in the workspace). The sections and wording are the same; the data is
read with frappe.get_all instead of REST, the PDF is rendered by wkhtmltopdf
instead of Chrome, and Kiluth Docs headings come from the live site.

Before anything is sent, every report is checked: a person's report holds only
their own email and name, the summary holds nobody's, and section 1 matches
the Signed certificates. Any failure sends nothing and opens a Task for Poom.

Manual run (System Manager), build only:

    bench --site portal.kiluth.com execute \
        kiluth_portal.kiluth_hr.learning_report.run --kwargs "{'month': '2026-10'}"

Pass `send=1` to email. `only=<email>` sends just that person (no summary).

The pure part (parse, resolve, analyse, HTML) imports nothing from Frappe, so
`tests/test_learning_report.py` runs it without a bench.
"""

from __future__ import annotations

import calendar
import collections
import datetime as dt
import html
import json
import os
import re

DOCS = "https://docs.kiluth.com"
SUMMARY_TO = "management@kiluth.com"
SWARM = "swarm@kiluth.com"
FAILURE_ASSIGNEE = "poom.pengcharoen@kiluth.com"
OPS_PROJECT = "PROJ-0001"
TITLE_RE = re.compile(r"^(?P<course>.+?) – (?P<email>\S+@\S+)$")
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learning_report_logo.svg")
_SENT_KEY = "kiluth_learning_report_last_sent_period"
# Reports start with October 2026 (first run 6 Nov, per hr/state). Never send or catch up on earlier
# months: on first deploy the hourly catch-up would otherwise send September's reports.
_FIRST_PERIOD = "2026-10"


# ─── Records ─────────────────────────────────────────────────────────────────

def parse_record(text):
	"""Score line plus the rows of the record's table: (question, right?, source)."""
	score = re.search(r"Result:\s*\*\*([^*]+)\*\*", text)
	lines = [l for l in text.splitlines() if l.startswith("|")]
	if len(lines) < 3:
		return (score.group(1) if score else ""), []
	head = [c.strip().lower() for c in lines[0].strip("|").split("|")]

	def col(*names):
		for n in names:
			if n in head:
				return head.index(n)
		return None

	qi, ri, si = col("question"), col("right?"), col("source")
	rows = []
	for l in lines[2:]:
		cells = [c.strip() for c in l.strip("|").split("|")]
		if qi is None or ri is None or len(cells) <= max(qi, ri):
			continue
		mark = cells[ri]
		rows.append({"question": cells[qi], "right": mark.startswith("✓"), "counted": mark in ("✓", "✗"),
			"source": cells[si] if si is not None and si < len(cells) else ""})
	return (score.group(1) if score else ""), rows


def group_findings(rows, start, end):
	"""Task rows with hygiene Fail → {email: [rows]}, for the month."""
	by = collections.defaultdict(list)
	for r in rows:
		if str(r["modified"])[:10] > str(end):
			continue
		# A finding belongs to whoever caused it: the person who completed the task
		# for a completion finding, else the person who wrote the task.
		done = re.search(r"completed by (\S+@\S+?),", r["hygiene_note"] or "")
		by[(done.group(1) if done else r["owner"] or "").lower()].append(r)
	return by


# ─── Kiluth Docs ─────────────────────────────────────────────────────────────

def _norm(x):
	return re.sub(r"[^a-z0-9 ]", "", x.lower().replace("&", "and")).strip()


def resolve(source, pages):
	"""Map a free-text test-record source to (page title, url, heading or None).
	Records write sources many ways: 'Retiring — step 5', 'How a task moves',
	'Working with Tasks §2'. Step and rule numbers are dropped; the page and
	heading are read from Kiluth Docs itself. pages: [(title, url, [headings])]."""
	s = re.sub(r"(§\s*\d+|\brules?\s*\d+|\bsteps?\s*[\d–-]+|\(.*?\))", "", source, flags=re.I)
	parts = [_norm(x) for x in re.split(r"\s+—\s+|[:;,]", s) if _norm(x)]
	if not parts:
		return None

	def heading_in(page, text):
		for h in page[2]:
			nh = _norm(h)
			if text and (nh == text or nh.startswith(text) or text.startswith(nh)):
				return h
		return None

	whole = _norm(s)
	exact = [p for p in pages if _norm(p[0]) == whole]
	if exact:
		return exact[0][0], exact[0][1], None
	head = parts[0]
	cands = [p for p in pages if _norm(p[0]) == head] or [p for p in pages if _norm(p[0]).startswith(head)]
	rest = parts[1:]
	if not cands:  # the source names only a section: find the page that has it
		cands = [p for p in pages if heading_in(p, head)]
		rest = parts
	if not cands:
		return None
	if len(cands) > 1 and rest:
		cands = [p for p in cands if heading_in(p, rest[0])] or cands
	page = cands[0]
	return page[0], page[1], (heading_in(page, rest[0]) if rest else None)


def missed_by_page(rows, pages):
	"""rows: iterable of (source, who). → [(title, url, Counter(section), times, people)] most missed first."""
	out = {}
	for src, who in rows:
		r = resolve(src, pages) or (src, None, None)
		e = out.setdefault(r[0], {"url": r[1], "sections": collections.Counter(), "times": 0, "people": set()})
		e["sections"][r[2] or ""] += 1
		e["times"] += 1
		e["people"].add(who)
	return sorted(((t, e["url"], e["sections"], e["times"], len(e["people"])) for t, e in out.items()),
		key=lambda x: (-x[3], x[0]))


def page_cell(title, url):
	return f"<a href='{DOCS}/{url}'>{html.escape(title)}</a>" if url else html.escape(title)


def sections_cell(sections):
	named = [html.escape(k) + (f" ×{n}" if n > 1 else "") for k, n in sections.most_common() if k]
	rest = sections.get("", 0)
	if rest:
		named.append("a step or rule on the page" + (f" ×{rest}" if rest > 1 else ""))
	return "<br>".join(named)


# ─── Analysis ────────────────────────────────────────────────────────────────

def month_bounds(month):
	y, m = map(int, month.split("-"))
	return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def analyse(month, certs, findings, pages):
	"""certs: Certificate Document rows with `record` text; findings: group_findings() output."""
	start, end = month_bounds(month)
	soon = end + dt.timedelta(days=61)
	kept = []
	for c in certs:
		m = TITLE_RE.match(c.get("title") or "")
		if not m:
			continue
		c = dict(c, course=m.group("course"), email=m.group("email").lower())
		c["score"], c["rows"] = parse_record(c.get("record") or "")
		c["in_month"] = start <= dt.date.fromisoformat(str(c["creation"])[:10]) <= end
		c["expiry_date"] = str(c["expiry_date"]) if c.get("expiry_date") else None
		kept.append(c)
	people = collections.defaultdict(lambda: {"held": [], "month": [], "all": []})
	for c in kept:
		p = people[c["email"]]
		p["all"].append(c)
		if c["status"] == "Signed":
			p["held"].append(c)
		if c["in_month"]:
			p["month"].append(c)
	for who in findings:
		if who.endswith("@kiluth.com") and who != SWARM:
			people[who]
	return {"start": start, "end": end, "soon": soon, "certs": kept, "people": dict(people),
		"findings": findings, "pages": pages}


def person_view(email, p, a):
	pages = a["pages"]
	missed = missed_by_page(((r["source"], email) for c in p["month"] for r in c["rows"]
		if r["counted"] and not r["right"] and r["source"]), pages)
	# Topics once missed, later answered right on the same source
	seen_wrong, fixed = set(), set()
	for c in sorted(p["all"], key=lambda c: str(c["creation"])):
		for r in c["rows"]:
			if not r["counted"] or not r["source"]:
				continue
			k = (resolve(r["source"], pages) or (r["source"],))[0]
			if not r["right"]:
				seen_wrong.add(k)
			elif k in seen_wrong:
				fixed.add(k)
	progress = collections.defaultdict(list)
	for c in sorted(p["all"], key=lambda c: str(c["creation"])):
		progress[c["course"]].append(c["score"].split("—")[0].strip() or c["status"])
	expiring = [c for c in p["held"] if c["expiry_date"] and dt.date.fromisoformat(c["expiry_date"]) <= a["soon"]]
	tasks = a["findings"].get(email, [])
	nxt = []
	for title, url, sections, _, _ in missed[:2]:
		top = sections.most_common(1)[0][0]
		where = f", section “{html.escape(top)}”" if top else ""
		nxt.append(f"Reread {page_cell(title, url)}{where}.")
	for c in expiring:
		nxt.append(f"Renew your {html.escape(c['course'])} certificate before {c['expiry_date']}.")
	if tasks and len(nxt) < 3:
		nxt.append(f"Fix the {len(tasks)} task{'s' if len(tasks) > 1 else ''} in section 5.")
	pending = {c["course"] for c in p["all"] if c["status"] == "Signed"}
	not_yet = [c["course"] for c in p["month"] if c["course"] not in pending]
	if not_yet and len(nxt) < 3:
		nxt.append(f"Retake {html.escape(not_yet[-1])} when ready — each try gets new questions.")
	return {"missed": missed, "fixed": fixed - {m[0] for m in missed}, "progress": progress, "expiring": expiring,
		"tasks": tasks, "next": nxt[:3]}


def has_action(p, v):
	"""Poom, 2026-10-26: email a person only when there is something to act on."""
	return bool(p["month"] or v["expiring"] or v["tasks"])


def summary_due(a):
	"""Skip the company summary when nobody took a test that month."""
	return any(c["in_month"] for c in a["certs"])


def docs_to_check(a):
	"""Sections missed by more than one person, or more than once: [(title, url, Counter, times, people)]."""
	misses = [(r["source"], c["email"]) for c in a["certs"] if c["in_month"]
		for r in c["rows"] if r["counted"] and not r["right"] and r["source"]]
	return [x for x in missed_by_page(misses, a["pages"]) if x[4] > 1 or x[3] > 1]


# ─── HTML ────────────────────────────────────────────────────────────────────

def logo_svg():
	with open(LOGO) as f:
		return f.read().strip()


STYLE = """
@page { size: A4; margin: 16mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #191615; font-size: 10pt; line-height: 1.45; margin: 0; }
.logo { width: 28mm; height: auto; }
h1 { font-size: 20pt; font-weight: 500; text-transform: uppercase; letter-spacing: .4px; margin: 10mm 0 1mm; }
.sub { font-size: 8.5pt; text-transform: uppercase; letter-spacing: .5px; color: #6b7785; }
h2 { font-size: 9pt; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; border-bottom: 1pt solid #191615; padding-bottom: 3px; margin: 7mm 0 2mm; }
table { width: 100%; border-collapse: collapse; }
td, th { text-align: left; padding: 4px 6px 4px 0; border-bottom: .5pt solid #e3e1db; vertical-align: top; }
th { font-size: 8pt; text-transform: uppercase; color: #6b7785; font-weight: 600; }
.note { font-size: 8.5pt; color: #6b7785; margin-top: 3px; }
.empty { color: #6b7785; }
ol { margin: 0; padding-left: 16px; }
a { color: inherit; }
"""


def page(title, sub, body):
	return f"<!doctype html><html><head><meta charset='utf-8'><style>{STYLE}</style></head><body>{logo_svg()}<h1>{title}</h1><div class='sub'>{sub}</div>{body}</body></html>"


def table(headers, rows, empty):
	if not rows:
		return f"<p class='empty'>{empty}</p>"
	th = "".join(f"<th>{h}</th>" for h in headers)
	tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
	return f"<table><tr>{th}</tr>{tr}</table>"


def _others_hidden(text, email):
	"""The task checker's notes can name the requester. A report names only its owner."""
	return re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", lambda m: m.group(0) if m.group(0).lower() == email else "a teammate", text)


def person_html(email, p, v, a):
	month = a["start"].strftime("%B %Y")
	held = [(html.escape(c["course"]), c["name"], c["expiry_date"] or "—") for c in p["held"]]
	att = [(html.escape(c["course"]), c["name"], html.escape(c["score"] or c["status"])) for c in p["month"]]
	topics = [(page_cell(t, u), sections_cell(sec), n) for t, u, sec, n, _ in v["missed"]]
	prog = [(html.escape(k), " → ".join(html.escape(x) for x in vals)) for k, vals in v["progress"].items()]
	tasks = [(t["name"], html.escape(_others_hidden(t["subject"] or "", email)),
		html.escape(_others_hidden((t["hygiene_note"] or "").split(" | ")[0], email))) for t in v["tasks"]]
	body = (
		"<h2>1. Certificates you hold</h2>" + table(["Course", "Certificate", "Valid until"], held, "None yet.")
		+ ("<p class='note'>Expiring within two months: " + ", ".join(html.escape(c["course"]) for c in v["expiring"]) + ".</p>" if v["expiring"] else "")
		+ f"<h2>2. Attempts in {month}</h2>" + table(["Course", "Record", "Result"], att, "No attempts this month.")
		+ "<h2>3. Topics to study</h2>" + table(["Doc", "Sections", "Questions missed"], topics, "Nothing missed this month.")
		+ "<h2>4. Progress</h2>" + table(["Course", "Results, oldest first"], prog, "No attempts yet.")
		+ ("<p class='note'>Docs once missed, now answered right: " + ", ".join(html.escape(s) for s in sorted(v["fixed"])) + ".</p>" if v["fixed"] else "")
		+ "<h2>5. Task habits</h2>" + table(["Task", "Title", "What the checker found"], tasks, "The task checker found nothing on your tasks this month.")
		+ "<h2>6. What to do next</h2>" + ("<ol>" + "".join(f"<li>{x}</li>" for x in v["next"]) + "</ol>" if v["next"] else "<p class='empty'>Nothing to do — keep going.</p>")
		+ f"<p class='note' style='margin-top:8mm'>This report is yours. It isn't a score, and other people see it only if you share it. How it's made: {DOCS}/hr/learning-report</p>"
	)
	return page("Learning Report", f"{month} · {html.escape(email)}", body)


def summary_html(a):
	month = a["start"].strftime("%B %Y")
	y0 = dt.date(a["start"].year, 1, 1)
	per = collections.defaultdict(lambda: [0, 0, 0, 0])
	for c in a["certs"]:
		d = dt.date.fromisoformat(str(c["creation"])[:10])
		passed = c["status"] in ("Signed", "Pending signature")
		if c["in_month"]:
			per[c["course"]][0] += 1; per[c["course"]][1] += passed
		if y0 <= d <= a["end"]:
			per[c["course"]][2] += 1; per[c["course"]][3] += passed
	rows = [(html.escape(k), f"{v[0]} / {v[1]}", f"{v[2]} / {v[3]}") for k, v in sorted(per.items())]
	misses, flawed = [], []
	for c in a["certs"]:
		if not c["in_month"]:
			continue
		for r in c["rows"]:
			if r["counted"] and not r["right"] and r["source"]:
				misses.append((r["source"], c["email"]))
			if not r["counted"] and "flawed" in r["question"].lower():
				flawed.append((html.escape(c["course"]), html.escape(r["question"][:90])))
	pages = missed_by_page(misses, a["pages"])
	missed = [(page_cell(t, u), sections_cell(sec), n, ppl) for t, u, sec, n, ppl in pages]
	check = [(page_cell(t, u), sections_cell(sec), n, ppl) for t, u, sec, n, ppl in pages if ppl > 1 or n > 1]
	exp = collections.Counter(c["course"] for c in a["certs"] if c["status"] == "Signed" and c["expiry_date"]
		and dt.date.fromisoformat(c["expiry_date"]) <= a["soon"])
	body = (
		"<h2>1. Attempts and passes</h2>" + table(["Course", f"{month}: attempts / passes", "Year to date"], rows, "No attempts.")
		+ "<h2>2. Most-missed docs</h2>" + table(["Doc", "Sections", "Times missed", "People"], missed, "Nothing missed.")
		+ "<h2>3. Docs to check</h2>" + table(["Doc", "Sections", "Times missed", "People"], check, "No doc stands out.")
		+ "<p class='note'>Docs missed by more than one person, or more than once. The department that owns the doc decides whether to fix it.</p>"
		+ "<h2>4. Flawed questions</h2>" + table(["Course", "Question"], flawed, "None this month.")
		+ "<h2>5. Certificates expiring in the next two months</h2>" + table(["Course", "Count"], [(html.escape(k), n) for k, n in exp.items()], "None.")
		+ f"<p class='note' style='margin-top:8mm'>No names in this summary. How it's made: {DOCS}/hr/learning-report</p>"
	)
	return page("Learning Report — Company", f"{month} · Kiluth LTD.", body)


# ─── Email ───────────────────────────────────────────────────────────────────

ASSETS = "/assets/kiluth_portal/"  # app public/: learning/ has the photos, certificate/ the logo and fonts
SANS = "Theinhardt,'Helvetica Neue',Arial,sans-serif"


def email_html(summary, label, assets):
	"""The email that carries a report PDF (design approved by Poom, 2026-10-27).

	Same look as the certificate email: a photo melting into black (the fade is
	in the JPG), white words, mint only on the label. Tables and inline styles so
	Gmail keeps it; the button's cell is #fefefe because Gmail on iPhone drops pure
	white. `assets` is the full URL of the app's public folder. Wording unchanged."""
	e = html.escape
	a = e(assets)
	f = f"{a}certificate/"
	if summary:
		hero, kicker, title = "hero-summary.jpg", "Company summary", "Learning report"
		line = f"The company learning summary for {e(label)} is attached.<br>No names."
	else:
		hero, kicker, title = "hero-person.jpg", "Learning report", "Learning report"
		line = (f"Your learning report for {e(label)} is attached.<br>"
			"It's yours: it isn't a score, and other people see it only if you share it.")
	pill = f"""<table role="presentation" cellpadding="0" cellspacing="0" align="center"><tr><td bgcolor="#fefefe" style="background-color:#fefefe;border-radius:999px">
<a class="k" href="{DOCS}/hr/learning-report" style="display:inline-block;padding:15px 30px;font-size:16px;font-family:{SANS};font-weight:300;text-decoration:none"><span style="color:#000000;text-decoration:none">How it's made</span></a></td></tr></table>"""
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
<title>{e(title)}: {e(label)}</title>
<style>
@font-face {{ font-family: 'Theinhardt'; src: url('{f}theinhardt-light.woff2') format('woff2'); font-weight: 300; }}
@font-face {{ font-family: 'Theinhardt'; src: url('{f}theinhardt-regular.woff2') format('woff2'); font-weight: 400; }}
body {{ margin: 0; padding: 0; background: #000; }}
/* frappe.sendmail wraps this in its standard template, whose email.css forces
   `.email-body a:not(.btn)` dark, bold and underlined, and its CSS inliner drops
   plain rules from this block. Rules inside @media survive, and these outrank
   that selector. They also cover the links iPhone Mail adds around dates. */
@media screen {{
  body .email-body a.k, body .email-body a[x-apple-data-detectors], body .email-body .nolink a {{
    color: inherit !important; font-weight: inherit !important; text-decoration: none !important; }}
  /* Its `.body-table td` font rule would put the system font back on every cell. */
  body .email-body .kl td {{ font-family: {SANS} !important; }}
}}
@media (max-width: 480px) {{
  .hero {{ padding-top: 180px !important; }}
  .h1 {{ font-size: 44px !important; }}
  .gut {{ padding-left: 20px !important; padding-right: 20px !important; }}
}}
</style></head>
<body id="body" style="margin:0;padding:0;background:#000">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#000000" style="background:#000"><tr><td align="center">
<table role="presentation" class="kl" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;font-family:{SANS};font-weight:300;color:#fff">
<tr><td background="{a}learning/{hero}" bgcolor="#000000" style="background-color:#000;background-image:url('{a}learning/{hero}');background-position:center top;background-size:100% auto;background-repeat:no-repeat">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="gut" style="padding:22px 24px"><img src="{f}logo-white.png" width="78" alt="Kiluth" style="display:block;width:78px;height:auto;border:0"></td></tr>
<tr><td align="center" class="hero gut" style="padding:260px 40px 0">
<div style="font-size:14px;letter-spacing:.18em;text-transform:uppercase;color:#7ee2a8">{e(kicker)}</div>
<div class="h1" style="font-size:56px;line-height:1.1;font-weight:400;letter-spacing:-.02em;padding:14px 0 18px;color:#fff"><span class="nolink">{e(label)}</span></div>
<div style="font-size:18px;line-height:1.7;color:#d6d6d6;padding-bottom:12px">{line}</div>
<div style="font-size:16px;line-height:1.7;color:#9a9a9a;padding-bottom:40px">— Kiluth</div></td></tr></table></td></tr>
<tr><td align="center" style="padding:8px 40px 56px">{pill}</td></tr>
<tr><td class="gut" style="padding:48px 40px;border-top:1px solid #1f1f1f"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:14px;line-height:2;color:#9a9a9a;vertical-align:top"><span style="color:#fff">{e(title)}</span><br>
<a class="k" href="{DOCS}/hr/learning-report" style="color:#9a9a9a;text-decoration:none">How it's made</a></td>
<td align="right" style="font-size:14px;line-height:2;color:#9a9a9a;vertical-align:top"><img src="{f}logo-white.png" width="64" alt="Kiluth" style="display:block;width:64px;height:auto;border:0;margin-left:auto">Kiluth LTD., Bangkok</td>
</tr></table></td></tr>
</table></td></tr></table></body></html>"""


# ─── Checks before sending ───────────────────────────────────────────────────

def check_reports(a, reports, summary, names):
	"""reports: {email: html}; summary: html or None; names: {email: full name}.
	Returns a list of problems; empty means safe to send."""
	problems = []
	everyone = set(a["people"]) | set(names)

	def mentions(text, who):
		hits = [who] if who.lower() in text.lower() else []
		full = (names.get(who) or "").strip()
		if len(full.split()) >= 2 and full.lower() in text.lower():
			hits.append(full)
		return hits

	for email, text in reports.items():
		for other in everyone - {email}:
			if mentions(text, other):
				problems.append(f"{email}'s report names {other}")
		signed = sum(1 for c in a["certs"] if c["email"] == email and c["status"] == "Signed")
		held = len(a["people"][email]["held"])
		if signed != held:
			problems.append(f"{email}'s report shows {held} certificates but {signed} are Signed")
	if summary is not None:
		for who in everyone:
			if mentions(summary, who):
				problems.append(f"the company summary names {who}")
	return problems


# ─── Portal side ─────────────────────────────────────────────────────────────

def _load_certs():
	import frappe

	rows = frappe.get_all("Document", filters={"document_type": "Certificate"},
		fields=["name", "title", "status", "effective_date", "expiry_date", "creation"], order_by="creation asc")
	for r in rows:
		files = frappe.get_all("File", filters={"attached_to_doctype": "Document", "attached_to_name": r["name"],
			"file_name": ["like", "%.md"]}, pluck="name", order_by="creation asc")
		content = frappe.get_doc("File", files[0]).get_content() if files else ""
		r["record"] = content.decode() if isinstance(content, bytes) else (content or "")
	return rows


def _load_findings(start, end):
	import frappe

	rows = frappe.get_all("Task", filters={"hygiene": "Fail", "modified": [">=", f"{start} 00:00:00"]},
		fields=["name", "subject", "hygiene", "hygiene_note", "owner", "status", "modified"], order_by="modified desc")
	return group_findings(rows, start, end)


def _heading_texts(page_html):
	out = []
	for m in re.finditer(r"<h[23][^>]*\bid=[^>]*>(.*?)(?:<a role=\"anchor\"|</h[23]>)", page_html, re.S):
		out.append(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip())
	return out


def _load_pages():
	"""Every Kiluth Docs page: (title, url path, [headings]), from the live site."""
	import requests

	index = requests.get(f"{DOCS}/static/contentIndex.json", timeout=30)
	index.raise_for_status()
	pages = []
	for slug, entry in index.json().items():
		parts = slug.split("/")
		if len(parts) != 3 or parts[2] != "index":
			continue
		url = "/".join(parts[:2])
		r = requests.get(f"{DOCS}/{url}", timeout=30)
		r.raise_for_status()
		pages.append((entry["title"].strip().strip('"'), url, _heading_texts(r.text)))
	if not pages:
		raise RuntimeError("Kiluth Docs returned no pages")
	return pages


def _full_names(emails):
	import frappe

	return {e: frappe.db.get_value("User", e, "full_name") or "" for e in emails}


def _pdf(page_html):
	from frappe.utils.pdf import get_pdf

	return get_pdf(page_html, {"page-size": "A4", "margin-top": "16mm", "margin-bottom": "18mm",
		"margin-left": "16mm", "margin-right": "16mm"})


def _send(to, subject, message, fname, pdf):
	import frappe

	frappe.sendmail(recipients=[to], subject=subject, message=message,
		attachments=[{"fname": fname, "fcontent": pdf}], delayed=False)


def _open_task(subject, description, assignee, department=None):
	"""One open Task per subject on PROJ-0001; reuse it if it's already there."""
	import frappe
	from frappe.desk.form.assign_to import add

	existing = frappe.get_all("Task", filters={"subject": subject, "project": OPS_PROJECT,
		"status": ["not in", ["Completed", "Cancelled"]]}, pluck="name", limit=1)
	if existing:
		return existing[0]
	doc = {"doctype": "Task", "subject": subject, "project": OPS_PROJECT, "status": "Open",
		"description": description}
	if department and frappe.db.exists("Department", department):
		doc["department"] = department
	t = frappe.get_doc(doc).insert(ignore_permissions=True)
	add({"doctype": "Task", "name": t.name, "assign_to": [assignee]})
	return t.name


def _flag_docs(month, flagged):
	"""One Task per owning department listing its docs to check. No names."""
	by_dept = collections.defaultdict(list)
	for title, url, sections, times, people in flagged:
		if url:
			by_dept[url.split("/")[0]].append((title, url, sections, times, people))
	made = []
	for folder, items in sorted(by_dept.items()):
		dept = "HR" if folder == "hr" else folder.replace("-", " ").title()
		lines = "".join(
			f"<li><a href='{DOCS}/{url}'>{html.escape(t)}</a>: "
			f"{sections_cell(sec).replace('<br>', '; ')}. Missed {n} time{'s' if n > 1 else ''} by {ppl} "
			f"{'people' if ppl > 1 else 'person'}.</li>"
			for t, url, sec, n, ppl in items)
		desc = (f"<p>The {month} learning report flagged these {dept} docs: many test answers missed the same "
			f"section, so it may be unclear.</p><ul>{lines}</ul><p>Check each section. Fix it if it's unclear, "
			f"per the <a href='{DOCS}/technology/kiluth-docs-style-guide'>Kiluth Docs Style Guide</a>, or comment "
			f"that it's clear. Done when every section is fixed or judged clear.</p>")
		made.append(_open_task(f"Check the {dept} docs flagged in the {month} learning report", desc, SWARM,
			f"{dept} - K"))
	return made


def build(month, send=False, only=None):
	"""Build every report for `month`; with send, check them and email them."""
	start, end = month_bounds(month)
	a = analyse(month, _load_certs(), _load_findings(start, end), _load_pages())
	label = a["start"].strftime("%B %Y")
	reports, skipped = {}, []
	for email, p in sorted(a["people"].items()):
		if only and email != only.lower():
			continue
		v = person_view(email, p, a)
		if not has_action(p, v):
			skipped.append(email)
			continue
		reports[email] = person_html(email, p, v, a)
	summary = summary_html(a) if not only and summary_due(a) else None
	problems = check_reports(a, reports, summary, _full_names(set(a["people"])))
	result = {"month": month, "reports": sorted(reports), "skipped": skipped, "summary": summary is not None,
		"problems": problems, "sent": False}
	if problems:
		raise RuntimeError("Learning report checks failed: " + "; ".join(problems))
	pdfs = {e: _pdf(h) for e, h in reports.items()}
	summary_pdf = _pdf(summary) if summary else None
	if not send:
		return result
	from frappe.utils import get_url

	assets = get_url(ASSETS)
	for email, pdf in pdfs.items():
		_send(email, f"Your Kiluth learning report — {label}", email_html(False, label, assets),
			f"Kiluth-Learning-Report-{month}-{email.split('@')[0]}.pdf", pdf)
	if summary_pdf:
		_send(SUMMARY_TO, f"Kiluth learning report, company summary — {label}", email_html(True, label, assets),
			f"Kiluth-Learning-Report-{month}-company.pdf", summary_pdf)
		result["flagged_tasks"] = _flag_docs(month, docs_to_check(a))
	result["sent"] = True
	return result


def _last_month():
	from frappe.utils import getdate, nowdate

	first = getdate(nowdate()).replace(day=1)
	return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def run(month=None, send=0, only=None):
	"""Manual run, System Manager only. Build only unless send=1."""
	import frappe

	frappe.only_for("System Manager")
	return build(month or _last_month(), send=bool(int(send)), only=only)


def send_monthly():
	"""Scheduled: 09:00 on the 6th, for last month. Sends once per month."""
	import frappe

	month = _last_month()
	if month < _FIRST_PERIOD:
		return
	if frappe.db.get_default(_SENT_KEY) == month:
		return
	user = frappe.session.user
	frappe.set_user(SWARM)
	try:
		build(month, send=True)
		frappe.db.set_default(_SENT_KEY, month)
	except Exception:
		frappe.db.rollback()
		frappe.set_user("Administrator")
		_open_task(f"Send the learning reports for {month} — automatic run failed",
			f"<p>The scheduled learning report for {month} failed. If the checks failed, nothing was sent. "
			f"Otherwise check the Email Queue for what went out before rerunning, so nobody gets theirs twice. "
			f"Completing or cancelling this task lets the hourly catch-up try again.</p><pre>{html.escape(frappe.get_traceback())}</pre>", FAILURE_ASSIGNEE)
		frappe.db.commit()
		frappe.log_error(title=f"Learning report {month} failed")
	finally:
		frappe.set_user(user)


def send_monthly_catchup():
	"""Hourly: runs send_monthly once the 6th 09:00 has passed, if it hasn't sent."""
	import frappe
	from frappe.utils import getdate, nowdate

	today, now = getdate(nowdate()), frappe.utils.now_datetime()
	if today.day < 6 or (today.day == 6 and now.hour < 9):
		return
	if _last_month() < _FIRST_PERIOD:
		return
	if frappe.db.get_default(_SENT_KEY) == _last_month():
		return
	# After a failure, wait until Poom closes the failure task instead of retrying every hour.
	if frappe.get_all("Task", filters={"subject": f"Send the learning reports for {_last_month()} — automatic run failed",
			"project": OPS_PROJECT, "status": ["not in", ["Completed", "Cancelled"]]}, limit=1):
		return
	send_monthly()
