"""Background jobs (Frappe's RQ queue). Wires dispatch.py to the outbox doctype."""

import json

import frappe

from kiluth_portal.task_notify import channels, dispatch, outbox

DOCTYPE = "Task Notification Outbox"
FIELDS = ["dedupe_key", "event_id", "event_type", "task", "actor", "recipient", "channel", "payload", "status", "attempts"]


class FrappeStore:
	def insert(self, row):
		doc = frappe.get_doc({"doctype": DOCTYPE, **row, "payload": json.dumps(row["payload"])})
		try:
			doc.insert(ignore_permissions=True)
		except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
			# Unique index on dedupe_key: this event was already written.
			frappe.db.rollback()
			return False
		frappe.db.commit()
		return True

	def update(self, key, **fields):
		frappe.db.set_value(DOCTYPE, {"dedupe_key": key}, fields, update_modified=True)
		frappe.db.commit()

	def failed(self):
		rows = frappe.get_all(DOCTYPE, filters={"status": outbox.FAILED}, fields=FIELDS, limit=500)
		for r in rows:
			r["payload"] = json.loads(r["payload"] or "{}")
		return rows


def _channels():
	return channels.enabled(frappe.conf.get("kiluth_notify_channels"))


def process(event):
	dispatch.process_event(event, FrappeStore(), _channels())


def retry_failed():
	dispatch.retry_failed(FrappeStore(), _channels())
