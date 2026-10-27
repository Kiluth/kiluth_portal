"""Kiluth's check on a passed certification test — implements
docs.kiluth.com/hr/certification, section "Kiluth's check".

A person's AI assistant saves a pass as a Certificate Document at
`Pending signature` with the test record attached as Markdown. This job then:

1. runs the checks that need no judgement, in code: the record says pass,
   10 counted questions all marked right, options and right answers present,
   sources written "Page title — Heading" with the page in the course and
   the heading on it today, named repeats pointing at earlier attempts
2. only if those pass, asks Claude on Amazon Bedrock the questions that need
   reading: the marked answer is what the section says, no other option is
   allowed, it tests a named decision, no unnamed repeats, a fair replacement
3. signs (certificate PDF attached as `signed_pdf`, status `Signed`) or voids
   with a plain-English comment. Either way the person gets an email: the
   certificate attached, or the reason it wasn't signed (`email_html`)

Our own failures (Bedrock error, malformed answer, PDF error, docs site down)
never void: the certificate stays `Pending signature` and a Task on PROJ-0001
asks Poom to look. Completing or cancelling that task lets the hourly sweep try
again.

The model id and a dry-run switch are on Certificate Check Settings. In dry
run the job comments what it would do and changes nothing.

Manual run (System Manager):

    bench --site portal.kiluth.com execute \
        kiluth_portal.kiluth_hr.certify.run --kwargs "{'name': 'CERT-00036'}"

Pass `dry_run=1` to only comment the verdict. A dry run still renders the
certificate PDF when it would sign, so a template error shows up there too.

The pure part (parse, code checks, docs text, prompt, verdict validation)
imports nothing from Frappe, so tests/test_certify.py runs it without a bench
and tests/bench_certify.py replays past certificates against Bedrock.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
from html.parser import HTMLParser

DOCS = "https://docs.kiluth.com"
SWARM = "swarm@kiluth.com"
FAILURE_ASSIGNEE = "poom.pengcharoen@kiluth.com"
DEFAULT_MODEL = "global.anthropic.claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8000
TITLE_RE = re.compile(r"^(?P<course>.+?) – (?P<email>\S+@\S+)$")
CERT_RE = re.compile(r"CERT-\d{5}")
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = os.path.join(HERE, "prompts", "certify_check.md")
TEMPLATE = os.path.join(HERE, "certificate_template.html")
PHOTO = os.path.join(HERE, "..", "public", "certificate", "photo.jpg")
ASSETS = "/assets/kiluth_portal/certificate/"  # email pictures and fonts, served by the Portal
RETAKE = "Retake the test when you're ready; a retake gets new questions."


# ─── The record ──────────────────────────────────────────────────────────────

def _cells(line):
	return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_record(text):
	"""The test record as written by the person's assistant.

	→ {"result", "passed", "rows": [{id, question, given, correct, mark,
	counted, right, source, repeats}], "options": {id: [(letter, text, bold)]},
	"columns": [...]}"""
	text = text or ""
	m = re.search(r"Result:\s*\*\*([^*]+)\*\*", text)
	result = m.group(1).strip() if m else ""
	lines = [l for l in text.splitlines() if l.strip().startswith("|")]
	rows, columns = [], []
	if len(lines) >= 3:
		columns = [c.lower() for c in _cells(lines[0])]

		def col(*names):
			for i, c in enumerate(columns):
				if any(c == n or c.startswith(n) for n in names):
					return i
			return None

		ix = {"id": col("#"), "question": col("question"), "given": col("answer given"),
			"correct": col("correct answer"), "mark": col("right?"), "source": col("source"),
			"repeats": col("repeats")}
		for l in lines[2:]:
			cells = _cells(l)
			get = lambda k: cells[ix[k]] if ix[k] is not None and ix[k] < len(cells) else ""
			mark = get("mark")
			rows.append({"id": get("id"), "question": get("question"), "given": get("given"),
				"correct": get("correct"), "mark": mark, "counted": mark in ("✓", "✗"),
				"right": mark == "✓", "source": get("source"), "repeats": get("repeats")})
	options = {}
	section = re.split(r"^##\s+Options\s*$", text, maxsplit=1, flags=re.M)
	if len(section) == 2:
		for line in section[1].splitlines():
			m = re.match(r"^\s*(\d+R?)\.\s+(.*)$", line)
			if not m:
				continue
			opts = []
			for part in m.group(2).split(" · "):
				part = part.strip()
				bold = part.startswith("**") and part.endswith("**")
				part = part.strip("*").strip()
				o = re.match(r"^([A-Z])\)\s*(.*)$", part)
				if o:
					opts.append((o.group(1), o.group(2), bold))
			options[m.group(1)] = opts
	passed = bool(re.search(r"\bpass\b", result, re.I)) and not re.search(r"not yet", result, re.I)
	return {"result": result, "passed": passed, "rows": rows, "options": options, "columns": columns}


# ─── Kiluth Docs ─────────────────────────────────────────────────────────────

def _norm(x):
	x = (x or "").replace("&", "and").replace("’", "'").replace("“", '"').replace("”", '"')
	return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", x.lower())).strip()


class _Text(HTMLParser):
	"""Quartz page HTML → plain text that keeps headings, lists and tables."""

	BLOCK = {"p", "div", "br", "ul", "ol", "table", "blockquote", "pre"}

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.out, self.headings, self.title = [], [], ""
		self._in_article = 0
		self._skip = 0
		self._heading = None
		self._row = None
		self._cell = None

	def handle_starttag(self, tag, attrs):
		a = dict(attrs)
		if tag == "article":
			self._in_article += 1
		if not self._in_article:
			return
		if tag in ("svg", "script", "style") or (tag == "a" and a.get("role") == "anchor"):
			self._skip += 1
		elif tag in ("h1", "h2", "h3", "h4"):
			self._heading = [tag, ""]
		elif tag == "tr":
			self._row = []
		elif tag in ("td", "th"):
			self._cell = ""
		elif tag == "li":
			self.out.append("\n- ")
		elif tag in self.BLOCK:
			self.out.append("\n")

	def handle_endtag(self, tag):
		if tag == "article":
			self._in_article -= 1
		if not self._in_article:
			return
		if tag in ("svg", "script", "style") or (tag == "a" and self._skip):
			self._skip = max(0, self._skip - 1)
		elif tag in ("h1", "h2", "h3", "h4") and self._heading:
			level, txt = int(self._heading[0][1]), self._heading[1].strip()
			if level == 1 and not self.title:
				self.title = txt
			else:
				self.headings.append(txt)
			self.out.append("\n\n" + "#" * level + " " + txt + "\n")
			self._heading = None
		elif tag in ("td", "th") and self._cell is not None and self._row is not None:
			self._row.append(re.sub(r"\s+", " ", self._cell).strip())
			self._cell = None
		elif tag == "tr" and self._row is not None:
			self.out.append("\n| " + " | ".join(self._row) + " |")
			self._row = None
		elif tag in ("p", "table"):
			self.out.append("\n")

	def handle_data(self, data):
		if not self._in_article or self._skip:
			return
		if self._heading is not None:
			self._heading[1] += data
		elif self._cell is not None:
			self._cell += data
		else:
			self.out.append(data)

	def text(self):
		return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()


def page_from_html(page_html):
	"""→ (title, [headings], text)."""
	p = _Text()
	p.feed(page_html)
	return p.title, p.headings, p.text()


def _slug(href):
	href = href.split("#")[0].split("?")[0]
	parts = [x for x in href.split("/") if x and x not in (".", "..")]
	return "/".join(parts)


class _CourseTable(HTMLParser):
	"""The Courses table on the Certification page: {course: {docs: [(title, slug)], must}}."""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.rows, self._row, self._cell, self._links, self._href = [], None, None, None, None

	def handle_starttag(self, tag, attrs):
		if tag == "tr":
			self._row = []
		elif tag in ("td", "th") and self._row is not None:
			self._cell, self._links = "", []
		elif tag == "a" and self._cell is not None:
			self._href = dict(attrs).get("href", "")
			self._links.append([self._href, ""])

	def handle_endtag(self, tag):
		if tag == "a":
			self._href = None
		elif tag in ("td", "th") and self._cell is not None:
			self._row.append((re.sub(r"\s+", " ", self._cell).strip(), self._links))
			self._cell = None
		elif tag == "tr" and self._row is not None:
			self.rows.append(self._row)
			self._row = None

	def handle_data(self, data):
		if self._cell is not None:
			self._cell += data
			if self._href is not None and self._links:
				self._links[-1][1] += data


def course_rows(certification_html):
	t = _CourseTable()
	t.feed(certification_html)
	out, head = {}, None
	for row in t.rows:
		names = [c[0].lower() for c in row]
		if "course" in names and any(n.startswith("docs the test draws from") for n in names):
			head = names
			continue
		if not head or len(row) != len(head):
			continue
		docs_i = next(i for i, n in enumerate(head) if n.startswith("docs the test draws from"))
		must_i = next((i for i, n in enumerate(head) if n.startswith("you must be able to")), None)
		course = row[head.index("course")][0]
		out[course] = {"docs": [(txt.strip(), _slug(h)) for h, txt in row[docs_i][1]],
			"must": row[must_i][0] if must_i is not None else ""}
	return out


# ─── Code checks ─────────────────────────────────────────────────────────────

def split_source(source):
	parts = [p.strip() for p in re.split(r"\s+—\s+", source or "")]
	return parts if len(parts) == 2 and all(parts) else None


def code_checks(rec, course, pages, earlier_names):
	"""rec: parse_record(); course: course_rows()[name]; pages: {slug: (title,
	headings, text)} for the course's docs; earlier_names: this person's
	earlier attempts at this course. Returns [(check, question id or "", why)]."""
	fails = []
	if not rec["rows"]:
		return [("record", "", "The test record has no question table.")]
	if not rec["passed"]:
		fails.append(("record", "", f"The record doesn't say pass (it says “{rec['result'] or 'nothing'}”)."))
	counted = [r for r in rec["rows"] if r["counted"]]
	if len(counted) != 10:
		fails.append(("record", "", f"The record has {len(counted)} counted questions, not 10. A flawed question must be replaced, not dropped."))
	wrong = [r["id"] for r in counted if not r["right"]]
	if wrong:
		fails.append(("record", ", ".join(wrong), "Not every counted answer is marked right."))
	if "correct answer" not in " ".join(rec["columns"]):
		fails.append(("record", "", "The record doesn't give the right answer for each question."))
	titles = {_norm(t): slug for t, slug in course["docs"]}
	for r in counted:
		q = r["id"]
		if not r["question"] or not r["given"]:
			fails.append(("record", q, "The question or the answer given is missing."))
		opts = rec["options"].get(q) or []
		if not 3 <= len(opts) <= 4:
			fails.append(("record", q, f"The record doesn't list the question's options (found {len(opts)}; a question has 3 or 4)."))
		else:
			bold = [o[0] for o in opts if o[2]]
			if len(bold) != 1:
				fails.append(("record", q, "The options don't mark exactly one right answer."))
			elif r["correct"] and r["correct"][:1].upper() != bold[0]:
				fails.append(("record", q, "The right answer in the table and in the options differ."))
		letters = [re.match(r"^([A-D])\b", x or "") for x in (r["given"], r["correct"])]
		if all(letters) and letters[0].group(1) != letters[1].group(1):
			fails.append(("record", q, "The answer given isn't the right answer, but it's marked right."))
		src = split_source(r["source"])
		if not src:
			fails.append(("source", q, f"The source “{r['source']}” isn't written “Page title — Heading”."))
			continue
		slug = titles.get(_norm(src[0]))
		if not slug:
			fails.append(("source", q, f"“{src[0]}” isn't one of this course's docs."))
			continue
		page = pages.get(slug)
		if not page or _norm(src[1]) not in {_norm(h) for h in page[1]}:
			fails.append(("source", q, f"“{src[0]}” has no heading “{src[1]}” today."))
		for ref in CERT_RE.findall(r["repeats"]):
			if ref not in earlier_names:
				fails.append(("repeat", q, f"It names {ref} as the earlier attempt it repeats, but that isn't one of your earlier attempts at this course."))
	return fails


def reason_from_code(fails):
	"""Plain-English void comment from code-check failures."""
	lines = []
	for _, q, why in fails[:6]:
		lines.append((f"Question {q}: " if q and "," not in q else (f"Questions {q}: " if q else "")) + why)
	more = f" ({len(fails) - 6} more.)" if len(fails) > 6 else ""
	return ("Kiluth's check couldn't confirm this test, so it can't become a certificate. "
		+ " ".join(lines) + more + " " + RETAKE)


# ─── The model ───────────────────────────────────────────────────────────────

VERDICT_TOOL = {
	"name": "record_verdict",
	"description": "Record Kiluth's check on the test: one entry per counted question, then the verdict.",
	"schema": {
		"type": "object",
		"properties": {
			"questions": {"type": "array", "items": {"type": "object", "properties": {
				"id": {"type": "string"},
				"answer_holds": {"type": "boolean", "description": "Check 1"},
				"only_one_allowed": {"type": "boolean", "description": "Check 2"},
				"tests_a_decision": {"type": "boolean", "description": "Check 3"},
				"unnamed_repeat_of": {"type": "string", "description": "Check 4: the earlier attempt and question it repeats without naming it, e.g. 'CERT-00013 Q6'; empty if none"},
				"note": {"type": "string", "description": "Why, quoting the doc; required when any check fails"},
			}, "required": ["id", "answer_holds", "only_one_allowed", "tests_a_decision", "unnamed_repeat_of", "note"]}},
			"replacement_fair": {"type": "boolean", "description": "Check 5; true when no question was flawed"},
			"verdict": {"type": "string", "enum": ["sign", "void"]},
			"reason_for_person": {"type": "string"},
		},
		"required": ["questions", "replacement_fair", "verdict", "reason_for_person"],
	},
}

SYSTEM = "You are Kiluth's certificate check. Follow the instructions in the message exactly and answer only by calling record_verdict."


def build_prompt(name, record, course_name, course, pages, certification_text, earlier):
	"""earlier: [(name, status, record text)] oldest first."""
	with open(PROMPT) as f:
		tpl = f.read()
	docs = "\n\n".join(f"### Doc: {pages[slug][0]} ({DOCS}/{slug})\n\n{pages[slug][2]}"
		for _, slug in course["docs"] if slug in pages)
	prev = "\n\n".join(f"### {n} ({s})\n\n{t}" for n, s, t in earlier) or "None. This is their first attempt at this course."
	fill = {"certification_page": certification_text, "course": course_name, "must": course["must"],
		"doc_titles": ", ".join(t for t, _ in course["docs"]), "course_docs": docs, "earlier": prev,
		"name": name, "record": record}
	for k, v in fill.items():
		tpl = tpl.replace("{{" + k + "}}", v)
	return tpl


def validate_verdict(v, rec):
	"""Return (verdict, reason, failed questions) or raise ValueError. A
	malformed or self-contradicting answer is our failure, never a sign."""
	if not isinstance(v, dict) or v.get("verdict") not in ("sign", "void"):
		raise ValueError(f"No valid verdict in the model's answer: {json.dumps(v)[:500]}")
	qs = v.get("questions")
	want = [r["id"] for r in rec["rows"] if r["counted"]]
	dropped = {r["id"] for r in rec["rows"] if not r["counted"]}
	if isinstance(qs, list):  # an entry for a flawed, uncounted question is harmless; ignore it
		qs = [q for q in qs if isinstance(q, dict) and str(q.get("id", "")).strip() not in dropped]
	if not isinstance(qs, list) or [str(q.get("id", "")).strip() for q in qs] != want:
		raise ValueError(f"The model's questions {[q.get('id') for q in qs or []]} don't match the record's {want}")
	bad = []
	for q in qs:
		if not all(isinstance(q.get(k), bool) for k in ("answer_holds", "only_one_allowed", "tests_a_decision")):
			raise ValueError(f"Question {q.get('id')}: a check isn't true or false")
		if not (q["answer_holds"] and q["only_one_allowed"] and q["tests_a_decision"]) or (q.get("unnamed_repeat_of") or "").strip():
			bad.append(q)
	if not isinstance(v.get("replacement_fair"), bool):
		raise ValueError("replacement_fair isn't true or false")
	should_sign = not bad and v["replacement_fair"]
	if (v["verdict"] == "sign") != should_sign:
		raise ValueError(f"The model's verdict '{v['verdict']}' contradicts its own per-question checks")
	reason = (v.get("reason_for_person") or "").strip()
	if v["verdict"] == "void" and not reason:
		raise ValueError("Void without a reason for the person")
	return v["verdict"], reason, bad


def model_notes(bad, replacement_fair):
	out = []
	for q in bad:
		failed = [n for k, n in (("answer_holds", "answer"), ("only_one_allowed", "one answer"),
			("tests_a_decision", "decision")) if not q[k]]
		if (q.get("unnamed_repeat_of") or "").strip():
			failed.append("repeats " + q["unnamed_repeat_of"].strip())
		out.append(f"Q{q['id']} ({', '.join(failed)}): {q.get('note', '').strip()}")
	if not replacement_fair:
		out.append("Replacement question not fair.")
	return out


def evaluate(name, title, record, earlier, certification_html, fetch, ask):
	"""The whole check for one certificate, with no Frappe.

	earlier: [(name, status, record)] this person's earlier attempts at the
	course, oldest first. fetch(slug) → page HTML. ask(system, user) → (tool
	input, usage). Returns {"verdict": sign|void, "reason", "by": code|model,
	"notes", "usage"}. Raises on our own failures (docs down, model error)."""
	m = TITLE_RE.match(title or "")
	if not m:
		return {"verdict": "void", "by": "code", "notes": [], "usage": {},
			"reason": f"The certificate's title “{title}” isn't “Course – company email”, so Kiluth's check can't tell which course it is. " + RETAKE}
	course_name = m.group("course")
	courses = course_rows(certification_html)
	course = courses.get(course_name)
	if not course:
		return {"verdict": "void", "by": "code", "notes": [], "usage": {},
			"reason": f"“{course_name}” isn't a course on the Certification page. " + RETAKE}
	pages = {}
	for _, slug in course["docs"]:
		pages[slug] = page_from_html(fetch(slug))
	if not record or not record.strip():
		return {"verdict": "void", "by": "code", "notes": [], "usage": {},
			"reason": "No test record is attached, so there's nothing to check. " + RETAKE}
	rec = parse_record(record)
	fails = code_checks(rec, course, pages, {n for n, _, _ in earlier})
	if not rec["passed"]:
		fails = [f for f in fails if f[0] == "record" and not f[1]] or fails
	if fails:
		return {"verdict": "void", "by": "code", "reason": reason_from_code(fails), "usage": {},
			"notes": [f"{c}{(' Q' + q) if q else ''}: {w}" for c, q, w in fails]}
	cert_text = page_from_html(certification_html)[2]
	prompt = build_prompt(name, record, course_name, course, pages, cert_text, earlier)
	answer, usage = ask(SYSTEM, prompt)
	verdict, reason, bad = validate_verdict(answer, rec)
	return {"verdict": verdict, "by": "model", "usage": usage, "answer": answer,
		"reason": (reason + ("" if "retake" in reason.lower() else " " + RETAKE)) if verdict == "void" else "",
		"notes": model_notes(bad, answer["replacement_fair"])}


# ─── Certificate PDF ─────────────────────────────────────────────────────────

def photo_uri():
	import base64

	with open(PHOTO, "rb") as f:
		return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def certificate_html(course, person, issued, expires, cert_id, font_faces="", photo=""):
	with open(TEMPLATE) as f:
		tpl = f.read()
	fill = {"font_faces": font_faces, "course": html.escape(course), "name": html.escape(person),
		"issued": html.escape(issued), "expires": html.escape(expires), "id": html.escape(cert_id),
		"photo": photo}
	for k, v in fill.items():
		tpl = tpl.replace("{{" + k + "}}", v)
	return tpl


def long_date(d):
	d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10])
	return f"{d.day} {d.strftime('%B %Y')}"


SANS = "Theinhardt,'Helvetica Neue',Arial,sans-serif"


def email_html(signed, course, first_name, assets, portal_url, cert_id="", expires="", reason=""):
	"""The person's email after Kiluth's check (design approved by Poom, 2026-10-27).

	Same look as the Growth Check email: a photo melting into black, white words,
	mint only on the "Certified" label. Tables and inline styles so Gmail keeps it;
	the button's cell is #fefefe because Gmail on iPhone drops pure white."""
	e = html.escape
	a = e(assets)
	if signed:
		hero, kicker, colour = "hero-signed.jpg", "Certified", "#7ee2a8"
		line = f"Every answer right, {e(first_name)}.<br>Your certificate is attached."
		button, href = "Open your certificate", portal_url
		middle = f"""<tr><td style="padding:0 40px 56px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #2a2a2a;border-bottom:1px solid #2a2a2a"><tr>
<td width="50%" style="padding:22px 0;vertical-align:top"><div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7a7a7a">Certificate No.</div><div class="nolink" style="font-size:18px;padding-top:6px;color:#fff"><span style="color:#ffffff;text-decoration:none">{e(cert_id)}</span></div></td>
<td width="50%" style="padding:22px 0 22px 24px;border-left:1px solid #2a2a2a;vertical-align:top"><div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7a7a7a">Valid until</div><div class="nolink" style="font-size:18px;padding-top:6px;color:#fff"><span style="color:#ffffff;text-decoration:none">{e(expires)}</span></div></td>
</tr></table>
<div style="font-size:16px;line-height:1.8;color:#9a9a9a;padding-top:24px">Certificates last a year, because the way we work keeps changing. Take the test again before it ends to keep it.</div></td></tr>"""
	else:
		hero, kicker, colour = "hero-not-signed.jpg", "Not signed", "#9a9a9a"
		line = f"Thanks for taking the test, {e(first_name)}.<br>Kiluth's check couldn't sign this one."
		button, href = "How to retake", f"{DOCS}/hr/certification#the-test"
		middle = f"""<tr><td class="gut" style="padding:0 40px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #2a2a2a;border-bottom:1px solid #2a2a2a"><tr>
<td style="padding:22px 0;vertical-align:top"><div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7a7a7a">Why</div><div style="font-size:18px;line-height:1.7;padding-top:6px;color:#ffffff">{e(reason)}</div></td>
</tr></table>
<div style="font-size:16px;line-height:1.8;color:#9a9a9a;padding-top:32px;text-align:center">Nothing counts against you.</div></td></tr>"""
	pill = f"""<table role="presentation" cellpadding="0" cellspacing="0" align="center" class="pill"><tr><td bgcolor="#fefefe" style="background-color:#fefefe;border-radius:999px">
<a class="k" href="{e(href)}" style="display:inline-block;padding:15px 30px;font-size:16px;font-family:{SANS};font-weight:300;text-decoration:none"><span style="color:#000000;text-decoration:none">{e(button)}</span></a></td></tr></table>"""
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
<title>{e(kicker)}: {e(course)}</title>
<style>
@font-face {{ font-family: 'Theinhardt'; src: url('{a}theinhardt-light.woff2') format('woff2'); font-weight: 300; }}
@font-face {{ font-family: 'Theinhardt'; src: url('{a}theinhardt-regular.woff2') format('woff2'); font-weight: 400; }}
body {{ margin: 0; padding: 0; background: #000; }}
/* frappe.sendmail wraps this in its standard template, whose email.css forces
   `.email-body a:not(.btn)` dark, bold and underlined, and its CSS inliner drops
   plain rules from this block. Rules inside @media survive, and these outrank
   that selector. They also cover the links iPhone Mail adds around dates. */
@media screen {{
  body .email-body a.k, body .email-body a[x-apple-data-detectors], body .email-body .nolink a {{
    color: inherit !important; font-weight: inherit !important; text-decoration: none !important; }}
}}
@media (max-width: 480px) {{
  .hero {{ padding-top: 200px !important; }}
  .h1 {{ font-size: 48px !important; }}
  .gut {{ padding-left: 20px !important; padding-right: 20px !important; }}
}}
</style></head>
<body id="body" style="margin:0;padding:0;background:#000">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#000000" style="background:#000"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;font-family:{SANS};font-weight:300;color:#fff">
<tr><td background="{a}{hero}" bgcolor="#000000" style="background-color:#000;background-image:url('{a}{hero}');background-position:center top;background-size:100% auto;background-repeat:no-repeat">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="gut" style="padding:28px 40px"><img src="{a}logo-white.png" width="78" alt="Kiluth" style="display:block;width:78px;height:auto;border:0"></td></tr>
<tr><td align="center" class="hero gut" style="padding:300px 40px 0">
<div style="font-size:14px;letter-spacing:.18em;text-transform:uppercase;color:{colour}">{e(kicker)}</div>
<div class="h1" style="font-size:64px;line-height:1.1;font-weight:400;letter-spacing:-.02em;padding:14px 0 18px;color:#fff">{e(course)}</div>
<div style="font-size:18px;line-height:1.7;color:#d6d6d6;padding-bottom:40px">{line}</div></td></tr></table></td></tr>
{"" if signed else middle}<tr><td align="center" style="padding:8px 40px 48px">{pill}</td></tr>
{middle if signed else ""}{_report_email().footer(assets.rsplit("certificate/", 1)[0], "You get this because you took a Kiluth certification test.",
	links=[("kiluth.com", "https://kiluth.com"), ("Portal", portal_url.split("/app/")[0]), ("How it works", f"{DOCS}/hr/certification")])}</table></td></tr></table></body></html>"""


# ─── Portal side ─────────────────────────────────────────────────────────────

def _settings():
	import frappe

	s = frappe.get_cached_doc("Certificate Check Settings")
	return {"enabled": bool(s.enabled), "dry_run": bool(s.dry_run),
		"model_id": (s.model_id or DEFAULT_MODEL).strip(), "max_tokens": int(s.max_tokens or DEFAULT_MAX_TOKENS)}


def _record(name):
	import frappe

	files = frappe.get_all("File", filters={"attached_to_doctype": "Document", "attached_to_name": name,
		"file_name": ["like", "%.md"]}, pluck="name", order_by="creation asc")
	if not files:
		return None
	content = frappe.get_doc("File", files[0]).get_content()
	return content.decode() if isinstance(content, bytes) else (content or "")


def _earlier(doc):
	import frappe

	rows = frappe.get_all("Document", filters={"document_type": "Certificate", "title": doc.title,
		"creation": ["<", doc.creation], "name": ["!=", doc.name]},
		fields=["name", "status"], order_by="creation asc")
	return [(r.name, r.status, _record(r.name) or "") for r in rows]


def _fetch(slug):
	import requests

	r = requests.get(f"{DOCS}/{slug}", timeout=30)
	r.raise_for_status()
	return r.text


def _failure_task(name, error):
	from kiluth_portal.kiluth_hr.learning_report import _open_task

	return _open_task(f"Check certificate {name} — automatic check failed",
		f"<p>Kiluth's automatic check on <a href='/app/document/{name}'>{name}</a> failed on our side, so the "
		f"certificate is still Pending signature. Nothing was signed or voided.</p><p>Fix the cause, or check it "
		f"by hand per docs.kiluth.com/hr/certification. Completing or cancelling this task lets the hourly sweep "
		f"try again.</p><pre>{html.escape(error)}</pre>", FAILURE_ASSIGNEE)


def _open_failure(name):
	import frappe

	return frappe.get_all("Task", filters={"subject": f"Check certificate {name} — automatic check failed",
		"project": "PROJ-0001", "status": ["not in", ["Completed", "Cancelled"]]}, limit=1)


def _person(doc, email):
	import frappe

	if doc.get("employee"):
		n = frappe.db.get_value("Employee", doc.employee, "employee_name")
		if n:
			return n
	return frappe.db.get_value("User", email, "full_name") or email


def _pdf(doc, course, email):
	from frappe.utils.pdf import get_pdf

	from kiluth_portal.utils.financial_report import _font_face_block

	page = certificate_html(course, _person(doc, email), long_date(doc.effective_date or doc.creation),
		long_date(doc.expiry_date) if doc.expiry_date else "", doc.name, _font_face_block(), photo_uri())
	return get_pdf(page, {"page-size": "A4", "orientation": "Landscape", "margin-top": "0mm",
		"margin-bottom": "0mm", "margin-left": "0mm", "margin-right": "0mm"})


def _sign(doc, pdf):
	import frappe
	from frappe.utils import nowdate

	f = frappe.get_doc({"doctype": "File", "file_name": f"{doc.name}.pdf", "attached_to_doctype": "Document",
		"attached_to_name": doc.name, "attached_to_field": "signed_pdf", "is_private": 1,
		"content": pdf}).insert(ignore_permissions=True)
	doc.signed_pdf = f.file_url
	doc.status = "Signed"
	doc.signed_date = nowdate()
	doc.flags.ignore_permissions = True
	doc.save()


def _void(doc, reason):
	doc.status = "Void"
	doc.flags.ignore_permissions = True
	doc.save()
	doc.add_comment("Comment", html.escape(reason))
	_email(doc, signed=False, reason=reason)


def _email(doc, signed, reason=""):
	"""Tell the person: the certificate attached, or why it wasn't signed."""
	import frappe
	from frappe.utils import get_url, get_url_to_form

	m = TITLE_RE.match(doc.title or "")
	if not m:
		return
	course, email = m.group("course"), (doc.get("employee_user") or m.group("email")).lower()
	first = _person(doc, email).split()[0]
	page = email_html(signed, course, first, get_url(ASSETS), get_url_to_form("Document", doc.name),
		cert_id=doc.name, expires=long_date(doc.expiry_date) if doc.expiry_date else "", reason=reason)
	attachments = []
	if signed and doc.signed_pdf:
		f = frappe.get_doc("File", {"file_url": doc.signed_pdf})
		attachments.append({"fname": f"Kiluth {course} certificate {doc.name}.pdf", "fcontent": f.get_content()})
	frappe.sendmail(recipients=[email], subject=f"You're certified: {course}" if signed else f"Not signed: {course}",
		message=page, attachments=attachments, reference_doctype="Document", reference_name=doc.name)


def check(cert, dry_run=None):
	"""The background job for one certificate. Never raises."""
	import frappe

	s = _settings()
	dry = s["dry_run"] if dry_run is None else bool(int(dry_run))
	user = frappe.session.user
	frappe.set_user(SWARM)
	try:
		name = cert
		doc = frappe.get_doc("Document", name)
		if doc.document_type != "Certificate" or doc.status != "Pending signature":
			return
		record = _record(name)
		age = frappe.utils.now_datetime() - frappe.utils.get_datetime(doc.creation)
		if record is None and age < dt.timedelta(days=1):
			return  # the assistant attaches the record just after saving; its File insert re-enqueues us
		m = TITLE_RE.match(doc.title or "")
		earlier = _earlier(doc)

		from kiluth_portal.utils.bedrock import ask_with_tool

		def ask(system, user_text):
			return ask_with_tool(system, user_text, VERDICT_TOOL, s["model_id"], s["max_tokens"])

		out = evaluate(name, doc.title, record or "", earlier, _fetch("hr/certification"), _fetch, ask)
		u = out.get("usage") or {}
		log = (f"Kiluth check{' (dry run)' if dry else ''}: {out['verdict']} by {out['by']}"
			+ (f", {s['model_id']}, {u.get('inputTokens', 0)} in / {u.get('outputTokens', 0)} out tokens" if out["by"] == "model" else "")
			+ "".join(f"<br>{html.escape(n)}" for n in out["notes"]))
		pdf = _pdf(doc, m.group("course"), m.group("email").lower()) if out["verdict"] == "sign" else None
		if dry:
			doc.add_comment("Info", log + (f"<br>Would comment: {html.escape(out['reason'])}" if out["reason"] else ""))
			frappe.db.commit()
			return out
		if frappe.db.get_value("Document", name, "status") != "Pending signature":
			return  # someone acted while the model was thinking
		doc.reload()
		if out["verdict"] == "sign":
			_sign(doc, pdf)
		else:
			_void(doc, out["reason"])
		doc.add_comment("Info", log)
		frappe.db.commit()
		return out
	except Exception:
		frappe.db.rollback()
		frappe.set_user("Administrator")
		_failure_task(cert, frappe.get_traceback())
		frappe.db.commit()
		frappe.log_error(title=f"Certificate check {cert} failed")
	finally:
		frappe.set_user(user)


def _enqueue(name):
	import frappe

	if not _settings()["enabled"]:
		return
	frappe.enqueue("kiluth_portal.kiluth_hr.certify.check", queue="long", timeout=900, cert=name,
		job_id=f"certify::{name}", deduplicate=True, enqueue_after_commit=True)


def on_document_update(doc, method=None):
	"""Document.on_update (runs on insert too): a certificate that just became
	Pending signature gets checked; one that just became Signed, by the check or
	by hand, emails the person their certificate."""
	if doc.document_type != "Certificate" or doc.status not in ("Pending signature", "Signed"):
		return
	before = doc.get_doc_before_save()
	if before and before.status == doc.status:
		return
	if doc.status == "Signed":
		_email(doc, signed=True)
	else:
		_enqueue(doc.name)


def on_file_insert(doc, method=None):
	"""File.after_insert: the assistant attaches the record after saving the Document."""
	import frappe

	if doc.attached_to_doctype != "Document" or not (doc.file_name or "").endswith(".md"):
		return
	row = frappe.db.get_value("Document", doc.attached_to_name, ["document_type", "status"], as_dict=True)
	if row and row.document_type == "Certificate" and row.status == "Pending signature":
		_enqueue(doc.attached_to_name)


def sweep():
	"""Hourly: re-enqueue certificates still pending after an hour (a lost job,
	a record attached late). Skips those with an open failure task, and in dry
	run those already commented, so a stuck one costs one model call, not 24."""
	import frappe

	s = _settings()
	if not s["enabled"]:
		return
	cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)
	for name in frappe.get_all("Document", filters={"document_type": "Certificate", "status": "Pending signature",
			"creation": ["<", cutoff]}, pluck="name"):
		if _open_failure(name):
			continue
		if s["dry_run"] and frappe.db.exists("Comment", {"reference_doctype": "Document", "reference_name": name,
				"comment_type": "Info", "content": ["like", "Kiluth check (dry run)%"]}):
			continue
		_enqueue(name)


def run(name, dry_run=0):
	"""Manual run, System Manager only."""
	import frappe

	frappe.only_for("System Manager")
	return check(name, dry_run=dry_run)


def _report_email():
	"""utils/report_email.py, also when tests load this file on its own."""
	try:
		from kiluth_portal.utils import report_email
	except ImportError:
		import importlib.util

		path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "utils", "report_email.py")
		spec = importlib.util.spec_from_file_location("report_email", path)
		report_email = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(report_email)
	return report_email
