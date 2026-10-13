"""Oracle: the listener pipe — events, dedupe, outbox states, failure isolation.

Runs without bench:  python -m unittest kiluth_portal.tests.test_task_notify_listener
"""

import json
import unittest

from kiluth_portal.task_notify import outbox
from kiluth_portal.task_notify.channels import CHANNELS, Channel, LogChannel, enabled
from kiluth_portal.task_notify.dispatch import guarded, process_event, retry_failed
from kiluth_portal.task_notify.events import ASSIGNED, COMMENTED, assignment_event, comment_event

POOM = "poom.pengcharoen@kiluth.com"
REAW = "phuttipan.samranruen@kiluth.com"


class MemoryStore:
	def __init__(self):
		self.rows = {}

	def insert(self, row):
		if row["dedupe_key"] in self.rows:
			return False
		self.rows[row["dedupe_key"]] = dict(row)
		return True

	def update(self, key, **fields):
		self.rows[key].update(fields)

	def failed(self):
		return [dict(r) for r in self.rows.values() if r["status"] == outbox.FAILED]

	def statuses(self):
		return sorted(r["status"] for r in self.rows.values())


class Recorder(Channel):
	def __init__(self, name="rec"):
		self.name = name
		self.sent = []

	def send(self, recipient, payload):
		self.sent.append((recipient, payload["title"]))


class Broken(Channel):
	name = "broken"

	def __init__(self, fail_times=99):
		self.fail_times = fail_times
		self.calls = 0

	def send(self, recipient, payload):
		self.calls += 1
		if self.calls <= self.fail_times:
			raise ConnectionError("push service down")


class BadStore(MemoryStore):
	def insert(self, row):
		raise RuntimeError("db gone")


def assigned(**kw):
	base = dict(
		todo="TD-1", reference_type="Task", task="TASK-0001", task_subject="Fix invoice", allocated_to=POOM,
		actor=REAW, actor_name="Reaw", status="Open", is_new=True, old_status=None, modified="2026-10-13 10:00:00",
	)
	base.update(kw)
	return assignment_event(**base)


def commented(**kw):
	base = dict(
		comment="CMT-1", reference_doctype="Task", task="TASK-0001", task_subject="Fix invoice", comment_type="Comment",
		commenter=REAW, commenter_name="Reaw", text=" Please check ", task_assign_json=json.dumps([POOM]),
	)
	base.update(kw)
	return comment_event(**base)


class Events(unittest.TestCase):
	def test_assignment_event_shape(self):
		e = assigned()
		self.assertEqual(e["event_type"], ASSIGNED)
		self.assertEqual(e["recipients"], [POOM])
		self.assertEqual(e["actor"], REAW)
		self.assertEqual(e["payload"]["url"], "/app/task/TASK-0001")
		self.assertEqual(e["payload"]["title"], "Reaw assigned you a task")
		self.assertEqual(e["payload"]["body"], "Fix invoice")

	def test_comment_event_shape(self):
		e = commented()
		self.assertEqual(e["event_type"], COMMENTED)
		self.assertEqual(e["recipients"], [POOM])
		self.assertEqual(e["payload"]["body"], "Please check")

	def test_no_recipients_means_no_event(self):
		self.assertIsNone(assigned(actor=POOM))
		self.assertIsNone(commented(commenter=POOM))
		self.assertIsNone(assigned(reference_type="Issue"))

	def test_event_survives_json(self):
		# It rides the RQ queue, so it must be plain data.
		for e in (assigned(), commented()):
			self.assertEqual(json.loads(json.dumps(e)), e)

	def test_same_save_same_id(self):
		self.assertEqual(assigned()["event_id"], assigned()["event_id"])
		self.assertEqual(commented()["event_id"], commented()["event_id"])

	def test_reassignment_later_is_a_new_event(self):
		later = assigned(is_new=False, old_status="Cancelled", modified="2026-10-14 09:00:00")
		self.assertNotEqual(assigned()["event_id"], later["event_id"])

	def test_comment_body_is_capped(self):
		self.assertEqual(len(commented(text="x" * 1000)["payload"]["body"]), 180)


class Dedupe(unittest.TestCase):
	def test_same_event_twice_notifies_once(self):
		store, rec = MemoryStore(), Recorder()
		process_event(assigned(), store, [rec])
		second = process_event(assigned(), store, [rec])
		self.assertEqual(len(rec.sent), 1)
		self.assertEqual(second, {})
		self.assertEqual(len(store.rows), 1)

	def test_key_differs_by_recipient_and_channel(self):
		k = outbox.dedupe_key
		self.assertEqual(len({k("e", POOM, "log"), k("e", REAW, "log"), k("e", POOM, "expo"), k("f", POOM, "log")}), 4)

	def test_one_row_per_recipient_per_channel(self):
		store = MemoryStore()
		e = commented(commenter="x@kiluth.com", task_assign_json=json.dumps([POOM, REAW]))
		process_event(e, store, [Recorder("a"), Recorder("b")])
		self.assertEqual(len(store.rows), 4)

	def test_actor_never_gets_a_row(self):
		store = MemoryStore()
		process_event(commented(task_assign_json=json.dumps([POOM, REAW])), store, [Recorder()])
		self.assertEqual([r["recipient"] for r in store.rows.values()], [POOM])


class OutboxStates(unittest.TestCase):
	def test_success_is_sent_after_one_attempt(self):
		store = MemoryStore()
		process_event(assigned(), store, [Recorder()])
		(row,) = store.rows.values()
		self.assertEqual((row["status"], row["attempts"], row["last_error"]), (outbox.SENT, 1, None))

	def test_row_keeps_what_was_asked(self):
		store = MemoryStore()
		process_event(assigned(), store, [Recorder()])
		(row,) = store.rows.values()
		self.assertEqual(
			(row["event_type"], row["task"], row["actor"], row["recipient"], row["channel"]),
			(ASSIGNED, "TASK-0001", REAW, POOM, "rec"),
		)

	def test_failure_is_failed_with_error(self):
		store = MemoryStore()
		process_event(assigned(), store, [Broken()])
		(row,) = store.rows.values()
		self.assertEqual((row["status"], row["attempts"]), (outbox.FAILED, 1))
		self.assertIn("push service down", row["last_error"])

	def test_retry_recovers(self):
		store, ch = MemoryStore(), Broken(fail_times=1)
		process_event(assigned(), store, [ch])
		retry_failed(store, [ch])
		(row,) = store.rows.values()
		self.assertEqual((row["status"], row["attempts"], row["last_error"]), (outbox.SENT, 2, None))

	def test_gives_up_after_max_attempts(self):
		store, ch = MemoryStore(), Broken()
		process_event(assigned(), store, [ch])
		for _ in range(outbox.MAX_ATTEMPTS + 3):
			retry_failed(store, [ch])
		(row,) = store.rows.values()
		self.assertEqual((row["status"], row["attempts"]), (outbox.DEAD, outbox.MAX_ATTEMPTS))
		self.assertEqual(ch.calls, outbox.MAX_ATTEMPTS)

	def test_retry_skips_sent_rows(self):
		store, rec = MemoryStore(), Recorder()
		process_event(assigned(), store, [rec])
		retry_failed(store, [rec])
		self.assertEqual(len(rec.sent), 1)

	def test_after_attempt_table(self):
		self.assertEqual(outbox.after_attempt(0, True), (outbox.SENT, 1))
		self.assertEqual(outbox.after_attempt(0, False), (outbox.FAILED, 1))
		self.assertEqual(outbox.after_attempt(outbox.MAX_ATTEMPTS - 1, False), (outbox.DEAD, outbox.MAX_ATTEMPTS))


class FailureIsolation(unittest.TestCase):
	def test_broken_channel_does_not_stop_others(self):
		store, rec = MemoryStore(), Recorder()
		process_event(assigned(), store, [Broken(), rec])
		self.assertEqual(len(rec.sent), 1)
		self.assertEqual(store.statuses(), [outbox.FAILED, outbox.SENT])

	def test_store_failure_does_not_raise(self):
		self.assertEqual(process_event(assigned(), BadStore(), [Recorder()]), {})

	def test_stub_channels_fail_cleanly(self):
		store = MemoryStore()
		process_event(assigned(), store, [CHANNELS["webpush"](), CHANNELS["expo"]()])
		self.assertEqual(store.statuses(), [outbox.FAILED, outbox.FAILED])

	def test_guarded_hook_never_raises(self):
		@guarded
		def hook(doc, method=None):
			raise RuntimeError("redis down")

		self.assertIsNone(hook(object()))

	def test_guarded_hook_passes_through_when_fine(self):
		self.assertEqual(guarded(lambda doc, method=None: "ok")(object()), "ok")


class Channels(unittest.TestCase):
	def test_default_is_log_only(self):
		self.assertEqual([c.name for c in enabled(None)], ["log"])

	def test_unknown_names_are_skipped(self):
		self.assertEqual([c.name for c in enabled(["log", "carrier-pigeon"])], ["log"])

	def test_named_stubs_exist(self):
		self.assertEqual(set(CHANNELS), {"log", "webpush", "expo"})

	def test_log_channel_sends(self):
		with self.assertLogs("kiluth_portal.task_notify", level="INFO") as logs:
			LogChannel().send(POOM, assigned()["payload"])
		self.assertIn(POOM, logs.output[0])


if __name__ == "__main__":
	unittest.main()
