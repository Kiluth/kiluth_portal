"""The listener's core: event in, outbox rows out, channels called. No frappe.

`store` is anything with:
  insert(row) -> bool       False if the dedupe_key already exists
  update(key, **fields)
  failed() -> list[row]     rows in Failed, for retry
`jobs.py` passes a store backed by the Task Notification Outbox doctype; the
oracle passes an in-memory one.

Nothing here raises. A broken channel marks its own row Failed and the next
row still goes out.
"""

import logging

from kiluth_portal.task_notify import outbox

logger = logging.getLogger("kiluth_portal.task_notify")


def _attempt(store, row, channel):
	try:
		channel.send(row["recipient"], row["payload"])
		ok, error = True, None
	except Exception as e:  # any channel bug stays inside its own row
		ok, error = False, f"{type(e).__name__}: {e}"[:500]
	status, attempts = outbox.after_attempt(row["attempts"], ok)
	store.update(row["dedupe_key"], status=status, attempts=attempts, last_error=error)
	return status


def process_event(event, store, channels):
	"""Write one outbox row per recipient per channel, then deliver each.

	Returns {dedupe_key: status} for rows written by this call. Rows that
	already existed (the same event seen again) are skipped, not re-sent.
	"""
	results = {}
	for recipient in event["recipients"]:
		for channel in channels:
			row = {
				"dedupe_key": outbox.dedupe_key(event["event_id"], recipient, channel.name),
				"event_id": event["event_id"],
				"event_type": event["event_type"],
				"task": event["task"],
				"actor": event["actor"],
				"recipient": recipient,
				"channel": channel.name,
				"payload": event["payload"],
				"status": outbox.QUEUED,
				"attempts": 0,
				"last_error": None,
			}
			try:
				if not store.insert(row):
					continue
				results[row["dedupe_key"]] = _attempt(store, row, channel)
			except Exception:
				logger.exception("task_notify: outbox write failed for %s", row["dedupe_key"])
	return results


def retry_failed(store, channels):
	"""Try every Failed row once more on its own channel."""
	by_name = {c.name: c for c in channels}
	results = {}
	for row in store.failed():
		channel = by_name.get(row["channel"])
		if channel is None:
			continue
		try:
			results[row["dedupe_key"]] = _attempt(store, row, channel)
		except Exception:
			logger.exception("task_notify: retry failed for %s", row["dedupe_key"])
	return results


def guarded(fn):
	"""Wrap a doc_events hook so nothing it does can stop a Task or Comment saving."""

	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except Exception:
			logger.exception("task_notify: hook %s failed; save continues", fn.__name__)
			return None

	wrapper.__name__ = fn.__name__
	wrapper.__doc__ = fn.__doc__
	return wrapper
