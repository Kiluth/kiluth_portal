"""When a new customer's name looks like one we already have, kept free of
Frappe so it can be tested on its own (python3 kiluth_portal/tests/test_customer_rules.py).

Why: on 2026-10-09 "Baanploypoom Kindergarten" was created next to the existing
"Baanploypoom" and had to be merged by hand (Poom, 2026-10-25).

The Frappe side (blocking the insert) is in customer.py.
"""

from __future__ import annotations

import re

# Words that say what kind of company it is, not which one.
LEGAL_WORDS = (
	"co", "company", "ltd", "limited", "inc", "plc", "corp", "corporation", "group", "thailand",
	"บริษัท", "จำกัด", "มหาชน", "ห้างหุ้นส่วน", "หจก", "บจก",
)
# Shorter than this, only an exact match counts: "CMCC" must not catch "CMCC Asia"-like noise
# from a two-letter fragment.
MIN_PART = 5


def normalize(name: str) -> str:
	words = re.findall(r"[0-9a-z฀-๿]+", (name or "").lower())
	text = " ".join(w for w in words if w not in LEGAL_WORDS)
	for w in LEGAL_WORDS:  # Thai is written without spaces: "บริษัทแมรี่จำกัด"
		if not w.isascii():
			text = text.replace(w, "")
	return re.sub(r"\s+", "", text)


def similar_customer(new: str, existing: list[str]) -> str | None:
	"""The first existing name that is the same once tidied, or contains / is contained by it."""
	n = normalize(new)
	if not n:
		return None
	for name in existing:
		e = normalize(name)
		if not e:
			continue
		if n == e:
			return name
		short, long = sorted((n, e), key=len)
		if len(short) >= MIN_PART and short in long:
			return name
	return None
