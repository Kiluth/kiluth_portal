"""The client brief from kiluth.com/brief/: checking what arrives, and its PDF.

The website sends the brief twice: `summary`, what a person reads (sections of
label → answers, already in the page's language), and `data`, the raw answers
for processing later. This module checks both and turns the summary into a PDF
in the Kiluth report design (utils/report_pdf.py). It imports nothing from
Frappe, so tests can run it alone; the report helper comes in as `rp`.
"""

from __future__ import annotations

import html as _html
import json
import re

PROJECT_RE = re.compile(r"^PROJ-\d{4}$")
THAI_RE = re.compile(r"[฀-๿]")
LIMITS = {"sections": 12, "lines": 16, "items": 40, "text": 500, "label": 80}
DATA_MAX = 60000
HERO = "email/hero-leaf-lit.jpg"
WORDS = {
	"th": {"label": "บรีฟโปรเจกต์", "none": "ยังไม่ระบุ", "test": "ทดสอบจาก staging"},
	"en": {"label": "Client brief", "none": "Not given", "test": "Test from staging"},
}


def _text(x, limit):
	return x.strip()[:limit] if isinstance(x, str) else ""


def clean_summary(raw):
	"""[[section, [[label, [answer, …]], …]], …] → the same, trimmed. ValueError if the shape is wrong."""
	if not isinstance(raw, list) or not raw:
		raise ValueError("summary must be a list of sections")
	out = []
	for sec in raw[: LIMITS["sections"]]:
		if not (isinstance(sec, list) and len(sec) == 2 and isinstance(sec[1], list)):
			raise ValueError("each section is [title, lines]")
		lines = []
		for line in sec[1][: LIMITS["lines"]]:
			if not (isinstance(line, list) and len(line) == 2 and isinstance(line[1], list)):
				raise ValueError("each line is [label, answers]")
			items = [t for t in (_text(i, LIMITS["text"]) for i in line[1][: LIMITS["items"]]) if t]
			lines.append((_text(line[0], LIMITS["label"]), items))
		out.append((_text(sec[0], LIMITS["label"]), lines))
	return out


def clean_data(raw):
	"""The raw answers: any JSON object, up to DATA_MAX characters once written out."""
	if not isinstance(raw, dict):
		raise ValueError("data must be an object")
	text = json.dumps(raw, ensure_ascii=False)
	if len(text) > DATA_MAX:
		raise ValueError("data too large")
	return raw


def field(data, key, limit=140):
	return _text(data.get(key), limit)


def file_base(project, date, test):
	day = date if re.match(r"^\d{4}-\d{2}-\d{2}$", date or "") else "undated"
	return ("TEST-" if test else "") + f"client-brief-{project}-{day}"


def t(s):
	"""Escaped text. Thai goes in its own font span with no tracking: wkhtmltopdf
	doesn't fall back to Plex inside a Theinhardt run, and letter-spacing pulls
	Thai tone marks off their letters."""
	e = _html.escape(s)
	return f"<span class='th' style='letter-spacing:0;text-transform:none'>{e}</span>" if THAI_RE.search(s) else e


def build_html(summary, meta, rp):
	"""The brief as the report design's HTML: photo cover, one numbered section per step."""
	w = WORDS["th" if meta.get("lang") == "th" else "en"]
	label = w["label"] + (f" · {w['test']}" if meta.get("test") else "")
	client = meta.get("client") or meta["project"]
	sub = " · ".join(x for x in (meta["project"], meta.get("by"), meta.get("date")) if x)
	none = f"<span class='muted'>{t(w['none'])}</span>"
	blocks = [
		rp.Table(t(title), ["", ""], [[t(k), "<br>".join(t(i) for i in items) or none] for k, items in lines], n=n)
		for n, (title, lines) in enumerate(summary, 1)
	]
	cover = rp.cover(rp.photo(HERO), t(label), t(client), t(sub))
	pages = rp.paginate(blocks, rp.CONTENT_END - rp.COVER_BODY_TOP, t(client), t(sub))
	return rp.document(f"{w['label']} {meta['project']}", cover, pages, foot_left=_html.escape(meta["project"]))
