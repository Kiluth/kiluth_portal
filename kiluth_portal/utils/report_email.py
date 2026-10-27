"""Email body shared by the two finance reports to Kiluth: the Monthly Financial
Report (`financial_report.py`) and the Close Report (`close_report.py`).

Same look as the certificate emails (`kiluth_hr/certify.py` `email_html`, design
approved by Poom 2026-10-27): a photo melting into black, white words, mint only
on the small label, Theinhardt, a white pill button. Tables and inline styles so
Gmail keeps it; the button's cell is #fefefe because Gmail on iPhone drops pure
white. The fade is baked into the JPGs in `public/email/`, never a CSS gradient.

Pure: no Frappe import, so `tests/test_report_email.py` runs without a bench.
The PDF each report attaches is built elsewhere and is not touched here.
"""

from __future__ import annotations

import html
import re

SANS = "Theinhardt,'Helvetica Neue',Arial,sans-serif"


def _rich(text: str) -> str:
	"""Escape, then turn **x** into white emphasis (the old emails' <strong>)."""
	return re.sub(r"\*\*(.+?)\*\*", r'<span style="color:#ffffff;font-weight:400">\1</span>', html.escape(text))


def footer(assets: str, why: str, portal_url: str = "https://portal.kiluth.com", links: list | None = None) -> str:
	"""The footer every Kiluth email ends with (design C, Poom 2026-10-27): links,
	why you got it, then a dark Kiluth wordmark. The wordmark is a dark-grey PNG,
	not a faded white logo: some email apps ignore CSS opacity.
	assets  the app's public folder URL, ending in "/"
	links   [(label, url)]; default kiluth.com, Portal, Docs"""
	e = html.escape
	link = lambda t, h: f'<a class="k" href="{h}" style="color:#9a9a9a;text-decoration:none">{t}</a>'
	dot = '<span style="color:#3a3a3a">&nbsp;&nbsp;·&nbsp;&nbsp;</span>'
	links = dot.join(link(e(t), e(h)) for t, h in (links or [
		("kiluth.com", "https://kiluth.com"), ("Portal", portal_url), ("Docs", "https://docs.kiluth.com")]))
	return f"""<tr><td class="gut" style="padding:40px 40px 0;border-top:1px solid #1f1f1f;font-family:{SANS};font-size:13px;line-height:1.8;color:#6a6a6a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="font-size:13px;color:#9a9a9a">{links}</td><td align="right" style="font-size:13px;color:#6a6a6a">Bangkok</td></tr></table>
<div style="padding-top:8px">{e(why)}</div></td></tr>
<tr><td class="gut" style="padding:40px 40px 40px"><img src="{e(assets)}email/wordmark-dark.png" width="115" alt="Kiluth" style="display:block;width:115px;height:auto;border:0"></td></tr>"""


def email_html(*, title: str, kicker: str, lines: list[str], hero: str, assets: str,
		portal_url: str, attachment: str = "", button: str = "", href: str = "",
		sign_off: str = "— Kiluth Portal", facts: list | None = None,
		why: str = "You get this because you work in the Kiluth Portal.") -> str:
	"""Build the email.

	title       big white heading, e.g. "Close Report"
	kicker      small mint label above it, e.g. "September 2026"
	lines       paragraphs, plain text; **x** marks the words the old email bolded
	hero        file in public/email/, e.g. "hero-close.jpg"
	assets      URL of the app's public folder, ending in "/"
	            (https://portal.kiluth.com/assets/kiluth_portal/)
	attachment  file name of the attached PDF, shown under the words
	button/href optional white pill
	why         the footer's one line on why this person gets the email
	facts       optional [(label, value)] rows shown under the words, e.g. a
	            leave request's dates; empty values show as "—"
	"""
	e = html.escape
	a = e(assets)
	body = "".join(
		f'<div style="font-size:18px;line-height:1.7;color:#d6d6d6;padding-bottom:14px">{_rich(t)}</div>'
		for t in lines
	)
	attached = ""
	if attachment:
		attached = f"""<tr><td class="gut" style="padding:0 40px 40px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #2a2a2a;border-bottom:1px solid #2a2a2a"><tr>
<td style="padding:22px 0;vertical-align:top"><div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7a7a7a">Attached</div><div class="nolink" style="font-size:16px;padding-top:6px;color:#fff;word-break:break-all"><span style="color:#ffffff;text-decoration:none">{e(attachment)}</span></div></td>
<td align="right" width="60" style="padding:22px 0;vertical-align:middle;font-size:12px;letter-spacing:.14em;color:#7ee2a8">PDF</td>
</tr></table></td></tr>"""
	rows = ""
	if facts:
		rows = "".join(
			f'<tr><td style="padding:14px 16px 14px 0;border-bottom:1px solid #1f1f1f;vertical-align:top;width:38%;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7a7a7a">{e(str(k))}</td>'
			f'<td class="nolink" style="padding:14px 0;border-bottom:1px solid #1f1f1f;vertical-align:top;font-size:16px;color:#ffffff"><span style="color:#ffffff;text-decoration:none">{e(str(v)) if v not in (None, "") else "—"}</span></td></tr>'
			for k, v in facts
		)
		rows = f"""<tr><td class="gut" style="padding:0 40px 40px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #2a2a2a">{rows}</table></td></tr>"""
	pill = ""
	if button and href:
		pill = f"""<tr><td align="center" style="padding:0 40px 48px"><table role="presentation" cellpadding="0" cellspacing="0" align="center"><tr><td bgcolor="#fefefe" style="background-color:#fefefe;border-radius:999px">
<a class="k" href="{e(href)}" style="display:inline-block;padding:15px 30px;font-size:16px;font-family:{SANS};font-weight:300;text-decoration:none"><span style="color:#000000;text-decoration:none">{e(button)}</span></a></td></tr></table></td></tr>"""
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
<title>{e(title)}: {e(kicker)}</title>
<style>
@font-face {{ font-family: 'Theinhardt'; src: url('{a}certificate/theinhardt-light.woff2') format('woff2'); font-weight: 300; }}
@font-face {{ font-family: 'Theinhardt'; src: url('{a}certificate/theinhardt-regular.woff2') format('woff2'); font-weight: 400; }}
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
  .h1 {{ font-size: 38px !important; }}
  .gut {{ padding-left: 20px !important; padding-right: 20px !important; }}
}}
</style></head>
<body id="body" style="margin:0;padding:0;background:#000">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#000000" style="background:#000"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;font-family:{SANS};font-weight:300;color:#fff">
<tr><td background="{a}email/{e(hero)}" bgcolor="#000000" style="background-color:#000;background-image:url('{a}email/{e(hero)}');background-position:center top;background-size:100% auto;background-repeat:no-repeat">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="gut" style="padding:28px 40px"><img src="{a}certificate/logo-white.png" width="78" alt="Kiluth" style="display:block;width:78px;height:auto;border:0"></td></tr>
<tr><td class="hero gut" style="padding:280px 40px 0">
<div class="nolink" style="font-size:14px;letter-spacing:.18em;text-transform:uppercase;color:#7ee2a8"><span style="color:#7ee2a8;text-decoration:none">{e(kicker)}</span></div>
<div class="h1" style="font-size:52px;line-height:1.1;font-weight:400;letter-spacing:-.02em;padding:14px 0 24px;color:#fff">{e(title)}</div>
{body}<div style="font-size:16px;line-height:1.7;color:#9a9a9a;padding:10px 0 40px">{e(sign_off)}</div></td></tr></table></td></tr>
{rows}{attached}{pill}{footer(assets, why, portal_url)}</table></td></tr></table></body></html>"""
