"""Outbox row rules: dedupe key and status moves. Pure, no frappe.

One row per (event, recipient, channel). Statuses:
  Queued  written, not tried yet
  Sent    channel accepted it (terminal)
  Failed  channel raised; retry_failed() tries again later
  Dead    gave up after MAX_ATTEMPTS (terminal)
"""

import hashlib

QUEUED, SENT, FAILED, DEAD = "Queued", "Sent", "Failed", "Dead"
TERMINAL = frozenset({SENT, DEAD})
MAX_ATTEMPTS = 5


def dedupe_key(event_id, recipient, channel):
	"""Unique per delivery. The doctype puts a unique index on it, so a second
	insert for the same event fails at the database, even across two workers."""
	raw = f"{event_id}|{recipient}|{channel}"
	return hashlib.sha256(raw.encode()).hexdigest()


def after_attempt(attempts, ok):
	"""(status, attempts) after one more try."""
	attempts += 1
	if ok:
		return SENT, attempts
	return (DEAD if attempts >= MAX_ATTEMPTS else FAILED), attempts
