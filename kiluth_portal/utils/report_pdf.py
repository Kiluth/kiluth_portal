"""The Kiluth report PDF design: black A4 pages, a photo cover, white type.

Same look as the certificate (design A, Poom 2026-10-27). Used by the Monthly
Financial Report, the Close Report and the Learning reports. Mockups:
workspace departments/technology/artifacts/email-redesign/report-pdfs/.

Rules for wkhtmltopdf (the Portal's PDF engine):
- Every page is a fixed 210 x 297 mm box with absolute positions. The page has
  no margins, so content can't flow across a page break; `paginate` splits
  the content into pages by estimated height instead.
- No flexbox, no CSS gradients. The photo fades are baked into the JPGs.
- Images are data URIs: Frappe's get_pdf disables local file access.
- `pdf()` must be used, not get_pdf directly: it sets zero margins and puts
  the fonts in.

The HTML builders import nothing from Frappe, so tests can run them alone.
"""

from __future__ import annotations

import base64
import html as _html
import os
import re

PUBLIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
FONTS_TOKEN = "/*kiluth-report-fonts*/"
MINT = "#7ee2a8"

# Vertical space, in mm. Content must end above the footer rule.
CONTENT_END = 268
COVER_BODY_TOP = 150
INNER_BODY_TOP = 54
WIDTH = 174  # page width less the 18 mm sides

LOGO = '<svg class="logo" viewBox="0 0 80 24" xmlns="http://www.w3.org/2000/svg"><path d="m16.724 23h-3.9539l-6.51834-9.5124-2.06294 1.6761v7.8363h-3.438233v-20.94457h3.438233v10.01387c.42023-.5158.84523-1.0315 1.27501-1.5472.42978-.5158.85956-1.03149 1.28934-1.54723l5.90233-6.91944h3.8823l-7.82197 9.16867zm5.7877-15.85885v15.85885h-3.3666v-15.85885zm-1.6618-6.07421c.5158 0 .9599.13848 1.3323.41545.3821.27697.5731.7545.5731 1.4326 0 .66854-.191 1.14607-.5731 1.43259-.3724.27697-.8165.41546-1.3323.41546-.5348 0-.9885-.13849-1.3609-.41546-.363-.28652-.5444-.76405-.5444-1.43259 0-.6781.1814-1.15563.5444-1.4326.3724-.27697.8261-.41545 1.3609-.41545zm9.8706 21.93306h-3.3809v-22.291214h3.3809zm18.6381-15.85885v15.85885h-2.6503l-.4584-2.1346h-.1863c-.3342.5444-.7592.9981-1.275 1.361-.5157.3534-1.0887.616-1.7191.7879-.6303.1815-1.2941.2722-1.9913.2722-1.1938 0-2.2158-.2005-3.0658-.6017-.8404-.4106-1.4851-1.041-1.934-1.891-.4488-.85-.6733-1.9483-.6733-3.295v-10.35765h3.3809v9.72735c0 1.232.2484 2.1537.745 2.7649.5062.6112 1.2893.9169 2.3495.9169 1.0219 0 1.8337-.2102 2.4354-.6304s1.0267-1.041 1.275-1.8624c.2578-.8213.3868-1.8289.3868-3.0227v-7.89365zm10.7302 13.42345c.4393 0 .8738-.0382 1.3036-.1146.4298-.086.8214-.1863 1.1748-.3009v2.5501c-.3725.1623-.8548.3008-1.447.4154-.5921.1146-1.2081.1719-1.848.1719-.8978 0-1.7048-.148-2.4211-.4441-.7163-.3056-1.2846-.8261-1.7048-1.5615s-.6303-1.7526-.6303-3.0514v-8.524h-2.1633v-1.50423l2.3208-1.18906 1.1031-3.39525h2.1203v3.52419h4.5413v2.56435h-4.5413v8.481c0 .8022.2006 1.3991.6017 1.7907s.9312.5874 1.5902.5874zm9.0683-19.855814v5.601454c0 .58259-.0191 1.15086-.0573 1.70479-.0286.55394-.0621.98372-.1003 1.28934h.1863c.3342-.55394.7449-1.00759 1.232-1.36097.4871-.36292 1.0315-.63512 1.6332-.81658.6112-.18146 1.2606-.27219 1.9483-.27219 1.2129 0 2.2444.20534 3.0944.61602.85.40112 1.4995 1.02669 1.9483 1.8767.4585.85005.6877 1.95315.6877 3.30925v10.3434h-3.3666v-9.713c0-1.232-.2531-2.1537-.7593-2.7649-.5062-.62081-1.2893-.93121-2.3495-.93121-1.0219 0-1.8337.21489-2.4354.64471-.5921.4202-1.0171 1.0458-1.275 1.8767-.2579.8213-.3868 1.8241-.3868 3.0084v7.8793h-3.3666v-22.291214z" fill="#ffffff"/></svg>'

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #000; }
body { font-family: 'Theinhardt', 'IBM Plex Sans Thai', 'Helvetica Neue', Arial, sans-serif; font-weight: 300; color: #fff; font-size: 9.5pt; line-height: 1.45; }
a { color: inherit; text-decoration: none; }
b, strong { font-weight: 400; color: #fff; }
.th { font-family: 'IBM Plex Sans Thai'; font-weight: 300; }
.page { position: relative; width: 210mm; height: 297mm; overflow: hidden; background: #000; page-break-after: always; }
.page.last { page-break-after: auto; }
.hero { position: absolute; left: 0; top: 0; width: 210mm; }
.logo { position: absolute; left: 18mm; top: 16mm; width: 24mm; height: 7.2mm; }
.cover { position: absolute; left: 18mm; right: 18mm; }
.label { font-size: 8.5pt; letter-spacing: 0.2em; text-transform: uppercase; color: #9a9a9a; }
.dot { color: #7ee2a8; }
.title { margin-top: 2mm; font-size: 40pt; font-weight: 400; letter-spacing: -0.02em; line-height: 1.05; }
.sub { margin-top: 3mm; font-size: 11pt; color: #bdbdbd; }
.body { position: absolute; left: 18mm; right: 18mm; }
.ptitle { font-size: 22pt; font-weight: 400; letter-spacing: -0.01em; }
.psub { margin-top: 1mm; font-size: 9.5pt; color: #9a9a9a; }
h2 { margin-top: 9mm; padding-bottom: 2mm; border-bottom: 0.5pt solid #3a3a3a; font-size: 7.5pt; font-weight: 300; letter-spacing: 0.16em; text-transform: uppercase; color: #9a9a9a; }
.body > h2:first-child, .c > h2:first-child { margin-top: 0; }
h2 .n { color: #7ee2a8; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
td, th { padding: 2.2mm 0; border-bottom: 0.5pt solid #1f1f1f; vertical-align: top; text-align: left; font-weight: 300; color: #e8e8e8; }
td + td, th + th { padding-left: 3mm; }
tr.bare th { padding: 0; border: 0; }
th { font-size: 7pt; letter-spacing: 0.14em; text-transform: uppercase; color: #7a7a7a; padding-top: 3mm; }
.r { text-align: right; }
tr.total td { color: #fff; font-weight: 400; border-bottom: 0.5pt solid #3a3a3a; }
tr.sec td { color: #9a9a9a; padding-top: 4mm; }
tr.ind td.first { padding-left: 4mm; }
.muted { color: #7a7a7a; }
.note { margin-top: 2mm; font-size: 8pt; color: #7a7a7a; }
.empty { padding: 2.2mm 0; color: #7a7a7a; border-bottom: 0.5pt solid #1f1f1f; }
.good { color: #7ee2a8; }
.bad { color: #ff9a8a; }
.kpi td { width: 50%; padding: 4.5mm 6mm 4.5mm 0; border-bottom: 0.5pt solid #2a2a2a; }
.kpi td + td { padding-left: 6mm; border-left: 0.5pt solid #2a2a2a; }
.kpi .k { font-size: 7.5pt; letter-spacing: 0.14em; text-transform: uppercase; color: #7a7a7a; }
.kpi .v { margin-top: 2mm; font-size: 22pt; font-weight: 400; letter-spacing: -0.01em; color: #fff; }
.kpi .d { margin-top: 1mm; font-size: 8.5pt; }
.strip td { padding: 4mm 4mm 0 0; border: 0; font-size: 11pt; color: #fff; }
.strip td + td { padding-left: 4mm; border-left: 0.5pt solid #3a3a3a; }
.strip .k { margin-bottom: 1.4mm; font-size: 7pt; letter-spacing: 0.14em; text-transform: uppercase; color: #7a7a7a; }
.foot { position: absolute; left: 18mm; right: 18mm; bottom: 12mm; border-top: 0.5pt solid #2a2a2a; padding-top: 3mm; font-size: 7.5pt; color: #6a6a6a; }
.foot td { border: 0; padding: 0; color: #6a6a6a; }
.cols td.c { width: 50%; padding: 0; border: 0; vertical-align: top; }
.cols td.c + td.c { padding-left: 8mm; }
ol { margin: 3mm 0 0 5mm; color: #e8e8e8; }
ol li { padding: 1.4mm 0; }
.legend { margin-top: 2mm; font-size: 8pt; color: #9a9a9a; }
.legend span { margin-right: 6mm; }
"""

# One column grid per column count, like kiluth-document's fixed label column:
# columns start at the same place in every table, so they line up down the page.
GRID = {1: [100], 2: [34, 66], 3: [34, 33, 33], 4: [34, 33, 16.5, 16.5], 5: [32, 17, 17, 17, 17]}


# ─── Assets and fonts ────────────────────────────────────────────────────────

def photo(rel):
	"""A photo from the app's public/ folder as a data URI, e.g. photo('email/hero-close.jpg')."""
	with open(os.path.join(PUBLIC, rel), "rb") as f:
		return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def font_faces(base_url):
	"""Theinhardt and IBM Plex Sans Thai, served by the Portal at /files/.

	wkhtmltopdf is flaky with data-URI fonts; a same-origin URL loads reliably.
	Plex is its own family listed after Theinhardt, so Thai and ฿ fall back to it."""
	base = base_url.rstrip("/")
	faces = [("Theinhardt", "theinhardt-light-webfont.ttf", 300), ("Theinhardt", "theinhardt-regular-webfont.ttf", 400),
		("IBM Plex Sans Thai", "IBMPlexSansThai-Light.ttf", 300), ("IBM Plex Sans Thai", "IBMPlexSansThai-Regular.ttf", 400)]
	return "\n".join(f"@font-face {{ font-family: '{fam}'; src: url('{base}/files/{f}') format('truetype'); "
		f"font-weight: {w}; font-style: normal; }}" for fam, f, w in faces)


def pdf(page_html):
	"""Render with the Portal's wkhtmltopdf: zero margins, fonts in."""
	from frappe.utils import get_url
	from frappe.utils.pdf import get_pdf

	return get_pdf(page_html.replace(FONTS_TOKEN, font_faces(get_url())),
		{"page-size": "A4", "margin-top": "0mm", "margin-bottom": "0mm", "margin-left": "0mm", "margin-right": "0mm"})


# ─── Pieces ──────────────────────────────────────────────────────────────────

def esc(x):
	return _html.escape(str(x))


def th(text):
	"""Thai text in its own font span: wkhtmltopdf doesn't fall back inside a Theinhardt run."""
	return f"<span class='th'>{text}</span>"


def heading(title, n=None):
	num = f"<span class='n'>{n:02d}</span>&nbsp;&nbsp;" if n else ""
	return f"<h2>{num}{title}</h2>"


def _attrs(i, right, first=False, width=None):
	cls = (["r"] if i in right else []) + (["first"] if first and i == 0 else [])
	a = " class='%s'" % " ".join(cls) if cls else ""
	return a + (" style='width:%s%%'" % width if width else "")


def _split(r):
	"""A row is a list of cells, or (cells, row_class) for 'total', 'sec' or 'ind'."""
	if isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], (list, tuple)):
		return r
	return r, ""


def table_html(head, rows, widths=None, right=()):
	"""`right`: indexes of the columns aligned right (amounts)."""
	w = widths or GRID[len(head)]
	h = "".join(f"<th{_attrs(i, right, width=w[i])}>{x}</th>" for i, x in enumerate(head))
	b = ""
	for r in rows:
		cells, kind = _split(r)
		cls = f" class='{kind}'" if kind else ""
		b += f"<tr{cls}>" + "".join(f"<td{_attrs(i, right, first=True)}>{x}</td>" for i, x in enumerate(cells)) + "</tr>"
	head_cls = "" if any(head) else " class='bare'"
	return f"<table><tr{head_cls}>{h}</tr>{b}</table>"


def _text_len(x):
	return len(_html.unescape(re.sub(r"<[^>]+>", "", str(x))))


def _row_height(cells, widths):
	lines = 1
	for x, w in zip(cells, widths):
		per_line = max(int(w / 100 * WIDTH * 0.52), 8)
		lines = max(lines, -(-_text_len(x) // per_line))
	return 3.4 + 4.9 * lines  # measured on the Portal's wkhtmltopdf: 8.3 mm a one-line row


class Table:
	"""A section: heading, table, optional note. Split across pages when it's long."""

	def __init__(self, title, head, rows, n=None, empty="", note="", widths=None, right=()):
		self.title, self.head, self.rows, self.n = title, head, rows, n
		self.empty, self.note, self.right = empty, note, right
		self.widths = widths or GRID[len(head)]

	def heights(self):
		top = 15 + (9 if any(self.head) else 0)
		return top, [_row_height(_split(r)[0], self.widths) + (1.8 if _split(r)[1] == "sec" else 0) for r in self.rows], (6 if self.note else 0)

	def render(self, rows, first=True, last=True):
		title = self.title if first else f"{self.title} (continued)"
		if not self.rows:
			body = f"<div class='empty'>{self.empty}</div>"
		else:
			body = table_html(self.head, rows, self.widths, self.right)
		note = f"<div class='note'>{self.note}</div>" if self.note and last else ""
		return heading(title, self.n) + body + note


class Block:
	"""Fixed HTML of a known height: a chart, a list, a note."""

	def __init__(self, html, height):
		self.html, self.height = html, height


class NewPage:
	"""Start a new inner page with this title. A soft one only leaves the cover:
	on an inner page it just carries on."""

	def __init__(self, title, sub="", soft=False):
		self.title, self.sub, self.soft = title, sub, soft


def paginate(blocks, first_space, title, sub):
	"""Fill pages with blocks. Returns [(page_title, page_sub, html)]; the first
	entry is the cover's body (its title and sub are None)."""
	pages = [[None, None, ""]]
	space = [first_space]
	cur = {"title": title, "sub": sub}

	def new_page(t=None, s=None):
		pages.append([t or cur["title"], s if s is not None else cur["sub"], ""])
		space.append(CONTENT_END - INNER_BODY_TOP)

	for b in blocks:
		if isinstance(b, NewPage):
			cur["title"], cur["sub"] = b.title, b.sub
			if b.soft and len(pages) > 1:
				continue
			if pages[-1][2] or len(pages) == 1:
				new_page(b.title, b.sub)
			else:
				pages[-1][0], pages[-1][1] = b.title, b.sub
			continue
		if isinstance(b, Block):
			if b.height > space[-1] and pages[-1][2]:
				new_page()
			pages[-1][2] += b.html
			space[-1] -= b.height
			continue
		top, rows_h, note_h = b.heights()
		if not b.rows:
			need = top + 8 + note_h
			if need > space[-1] and pages[-1][2]:
				new_page()
			pages[-1][2] += b.render([])
			space[-1] -= need
			continue
		i, first = 0, True
		while i < len(b.rows):
			fit, used = 0, top
			while i + fit < len(b.rows) and used + rows_h[i + fit] + (note_h if i + fit == len(b.rows) - 1 else 0) <= space[-1]:
				used += rows_h[i + fit]
				fit += 1
			# Keep at least two rows with the heading; a lone heading moves to the next page.
			if fit < min(2, len(b.rows) - i) and pages[-1][2]:
				new_page()
				continue
			fit = max(fit, 1)
			# Don't leave one row alone on the next page.
			if len(b.rows) - (i + fit) == 1 and fit > 2:
				fit -= 1
			last = i + fit == len(b.rows)
			pages[-1][2] += b.render(b.rows[i:i + fit], first, last)
			space[-1] -= used + (note_h if last else 0)
			i += fit
			first = False
			if not last:
				new_page()
	return pages


def cover(hero, label, title, sub, top=96):
	return (f"<img class='hero' src='{hero}' alt=''>{LOGO}"
		f"<div class='cover' style='top:{top}mm'><div class='label'><span class='dot'>&#9679;</span>&nbsp;&nbsp;{label}</div>"
		f"<div class='title'>{title}</div><div class='sub'>{sub}</div></div>")


def document(doc_title, cover_html, pages, foot_left="Bangkok", body_top=COVER_BODY_TOP):
	"""cover_html + the pages from `paginate` → the full HTML document."""
	total = len(pages)
	out = []
	for i, (t, s, body) in enumerate(pages, 1):
		cls = "page last" if i == total else "page"
		foot = (f"<div class='foot'><table><tr><td>{foot_left}</td>"
			f"<td class='r'>Kiluth LTD. · Confidential · {i} / {total}</td></tr></table></div>")
		if i == 1:
			out.append(f"<div class='{cls}'>{cover_html}<div class='body' style='top:{body_top}mm'>{body}</div>{foot}</div>")
		else:
			head = f"<div class='ptitle'>{t}</div>" + (f"<div class='psub'>{s}</div>" if s else "")
			out.append(f"<div class='{cls}'>{LOGO}<div class='body' style='top:36mm'>{head}{body}</div>{foot}</div>")
	return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(doc_title)}</title>"
		f"<style>{FONTS_TOKEN}{CSS}</style></head><body>{''.join(out)}</body></html>")


# ─── Small charts (SVG in mm) ────────────────────────────────────────────────

def sparkline(vals, w=60, h=10):
	if len(vals) < 2:
		return ""
	lo, hi = min(vals), max(vals)
	span = (hi - lo) or 1
	pts = [(i * w / (len(vals) - 1), h - (v - lo) / span * h) for i, v in enumerate(vals)]
	line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
	lx, ly = pts[-1]
	return (f"<svg width='{w}mm' height='{h}mm' viewBox='-1 -1 {w + 2} {h + 2}' style='margin-top:3mm' xmlns='http://www.w3.org/2000/svg'>"
		f"<polyline points='{line}' fill='none' stroke='#bdbdbd' stroke-width='0.5'/>"
		f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='1' fill='{MINT}'/></svg>")
