"""The rules behind website lead routing, kept free of Frappe so they can be
tested on their own (python3 kiluth_portal/tests/test_lead_rules.py).

- least_loaded: who gets the next lead.
- one_working_day_after: when an untouched lead escalates.
- escalation_target: who it escalates to.

The Frappe side (who is in Sales, what counts as touched) is in lead_routing.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def least_loaded(loads: list[tuple[str, int, datetime | None]]) -> str | None:
	"""Pick from (user, open qualify-lead tasks, when they were last given one).

	Fewest open first. On a tie, whoever was given a lead longest ago (never
	counts as longest ago), then by name, so the pick is the same every time.
	"""
	if not loads:
		return None
	return min(loads, key=lambda r: (r[1], r[2] or datetime.min, r[0]))[0]


def escalation_target(holders: list[str], executives: list[str]) -> str | None:
	"""Who an untouched lead moves to, or None to leave it where it is.

	Only ever one person, and only when the role names exactly one: picking
	between several would be a rule nobody has made. None too when that person
	is already the only one on it.
	"""
	people = set(executives)
	if len(people) != 1:
		return None
	person = next(iter(people))
	return None if set(holders) == {person} else person


def is_working_day(day: date, holidays: set[date]) -> bool:
	return day.weekday() < 5 and day not in holidays


def one_working_day_after(start: datetime, holidays: set[date]) -> datetime:
	"""The same clock time on the next working day after `start`'s date.

	Friday 17:00 → Monday 17:00; Saturday 10:00 → Monday 10:00; a public
	holiday in between is skipped. This is the website's promise: a person
	replies within one working day.
	"""
	day = start.date() + timedelta(days=1)
	while not is_working_day(day, holidays):
		day += timedelta(days=1)
	return datetime.combine(day, start.time())
