"""Oracle: people-only notifications (TASK-2026-00151).

Runs without bench:  python -m unittest kiluth_portal.tests.test_task_notify_quiet
"""

import unittest

from kiluth_portal.task_notify import quiet
from kiluth_portal.task_notify.digest import due_event, wording
from kiluth_portal.task_notify.dispatch import process_event
from kiluth_portal.task_notify.events import assignment_event, comment_event
from kiluth_portal.tests.test_task_notify_listener import MemoryStore, Recorder

POOM = "poom.pengcharoen@kiluth.com"
REAW = "phuttipan.samranruen@kiluth.com"
SWARM = "swarm@kiluth.com"
ON = {"kiluth_people_only_notify": [POOM]}
REMOVED = "Your assignment on <b>Task</b> <b>Fix it</b> has been removed by <b>Kiluth Swarm</b>"
ASSIGNED_SUBJ = "<b>Kiluth Swarm</b> assigned a new task <b>Task</b> <b>Fix it</b> to you"


def assigned(actor, to=POOM):
	return assignment_event(todo="T1", reference_type="Task", task="TASK-1", task_subject="Fix it", allocated_to=to,
		actor=actor, actor_name=actor, status="Open", is_new=True, old_status=None, modified="m")


def commented(commenter, assign=f'["{POOM}"]', mentioned=(), from_check=False, requester=None):
	return comment_event(comment="C1", reference_doctype="Task", task="TASK-1", task_subject="Fix it", comment_type="Comment",
		commenter=commenter, commenter_name=commenter, text="hi", task_assign_json=assign, requester=requester,
		from_check=from_check, mentioned=mentioned)


def run(event, conf):
	people_only, bots = quiet.settings(conf)
	chans = [Recorder("webpush"), Recorder("log"), Recorder("bell")]
	process_event(event, MemoryStore(), chans, who=lambda e: quiet.recipients(e, people_only),
		allow=lambda c, r, e: quiet.allowed(c, r, e, people_only, bots))
	return {c.name: sorted(r for r, _ in c.sent) for c in chans}


class Settings(unittest.TestCase):
	def test_off_by_default(self):
		self.assertEqual(quiet.settings({}), (set(), {SWARM}))

	def test_bots_configurable(self):
		self.assertEqual(quiet.settings({"kiluth_notify_bots": ["bot@x"]})[1], {"bot@x"})

	def test_system_users_are_bots(self):
		for u in (None, "", "Administrator", "Guest", SWARM):
			self.assertTrue(quiet.is_bot(u, {SWARM}))
		self.assertFalse(quiet.is_bot(REAW, {SWARM}))


class NotificationLog(unittest.TestCase):
	def test_removed_dropped_for_listed_user_only(self):
		self.assertTrue(quiet.drop_log(for_user=POOM, log_type="Assignment", subject=REMOVED, people_only={POOM}))
		self.assertFalse(quiet.drop_log(for_user=REAW, log_type="Assignment", subject=REMOVED, people_only={POOM}))
		self.assertFalse(quiet.drop_log(for_user=POOM, log_type="Assignment", subject=REMOVED, people_only=set()))

	def test_new_assignment_kept(self):
		self.assertFalse(quiet.drop_log(for_user=POOM, log_type="Assignment", subject=ASSIGNED_SUBJ, people_only={POOM}))

	def test_no_email_for_listed_user(self):
		self.assertFalse(quiet.email_log(for_user=POOM, people_only={POOM}))
		self.assertTrue(quiet.email_log(for_user=REAW, people_only={POOM}))

	def test_summary_keeps_people_only(self):
		bots = {SWARM}
		self.assertTrue(quiet.in_summary(log_type="Assignment", from_user=REAW, subject="Reaw assigned", bots=bots))
		self.assertTrue(quiet.in_summary(log_type="Mention", from_user=REAW, subject="x", bots=bots))
		self.assertFalse(quiet.in_summary(log_type="Assignment", from_user=SWARM, subject=ASSIGNED_SUBJ, bots=bots))
		self.assertFalse(quiet.in_summary(log_type="Alert", from_user=None, subject="Task check on", bots=bots))
		self.assertFalse(quiet.in_summary(log_type="Assignment", from_user=REAW, subject=REMOVED, bots=bots))


class Push(unittest.TestCase):
	def test_off_nothing_changes(self):
		self.assertEqual(run(assigned(SWARM), {}), {"webpush": [POOM], "log": [POOM], "bell": [POOM]})
		self.assertEqual(run(commented(SWARM, from_check=True), {}), {"webpush": [POOM], "log": [POOM], "bell": [POOM]})

	def test_swarm_hand_back_no_push_bell_kept(self):
		self.assertEqual(run(assigned(SWARM), ON), {"webpush": [], "log": [], "bell": [POOM]})

	def test_person_assigns_pushes(self):
		self.assertEqual(run(assigned(REAW), ON), {"webpush": [POOM], "log": [POOM], "bell": [POOM]})

	def test_task_check_no_push_bell_kept(self):
		e = commented(SWARM, assign=f'["{REAW}"]', from_check=True, requester=POOM)
		self.assertEqual(run(e, ON), {"webpush": [REAW], "log": [REAW], "bell": sorted([POOM, REAW])})

	def test_person_comment_without_mention_no_push(self):
		self.assertEqual(run(commented(REAW), ON), {"webpush": [], "log": [], "bell": [POOM]})

	def test_person_comment_with_mention_pushes(self):
		self.assertEqual(run(commented(REAW, mentioned=[POOM]), ON), {"webpush": [POOM], "log": [POOM], "bell": [POOM]})

	def test_mention_on_task_not_assigned_pushes_no_extra_bell(self):
		e = commented(REAW, assign="[]", mentioned=[POOM])
		self.assertEqual(run(e, ON), {"webpush": [POOM], "log": [POOM], "bell": []})

	def test_mention_of_unlisted_user_adds_nothing(self):
		e = commented(POOM, assign="[]", mentioned=[REAW])
		self.assertEqual(run(e, ON), {"webpush": [], "log": [], "bell": []})

	def test_swarm_mention_no_push(self):
		self.assertEqual(run(commented(SWARM, mentioned=[POOM]), ON), {"webpush": [], "log": [], "bell": [POOM]})

	def test_others_unchanged_when_on(self):
		self.assertEqual(run(assigned(SWARM, to=REAW), ON), {"webpush": [REAW], "log": [REAW], "bell": [REAW]})
		self.assertEqual(run(commented(POOM, assign=f'["{REAW}"]'), ON), {"webpush": [REAW], "log": [REAW], "bell": [REAW]})

	def test_due_today_pushes(self):
		e = due_event(user=POOM, task="TASK-1", subject="Fix it", day="2026-11-09")
		self.assertEqual(run(e, ON)["webpush"], [POOM])

	def test_due_same_day_once(self):
		store, ch = MemoryStore(), Recorder("webpush")
		for _ in range(2):
			process_event(due_event(user=POOM, task="TASK-1", subject="Fix it", day="2026-11-09"), store, [ch])
		self.assertEqual(len(ch.sent), 1)


class Events(unittest.TestCase):
	def test_mentions_only_from_real_comments(self):
		e = comment_event(comment="C1", reference_doctype="Task", task="TASK-1", task_subject="x", comment_type="Info",
			commenter=REAW, commenter_name="Reaw", text="", task_assign_json="[]", mentioned=[POOM])
		self.assertIsNone(e)

	def test_self_mention_ignored(self):
		self.assertIsNone(commented(POOM, assign="[]", mentioned=[POOM]))


class Summary(unittest.TestCase):
	def test_nothing_no_email(self):
		self.assertIsNone(wording("Poom", [], [], "Monday 9 November 2026"))

	def test_counts_in_subject(self):
		w = wording("Poom", ["Reaw assigned you X."], ["Fix it (TASK-1).", "Ship (TASK-2)."], "Monday 9 November 2026")
		self.assertEqual(w["subject"], "Your Kiluth Tasks: 1 from a person, 2 due today")
		self.assertIn("**Due today:**", w["lines"])


if __name__ == "__main__":
	unittest.main()
