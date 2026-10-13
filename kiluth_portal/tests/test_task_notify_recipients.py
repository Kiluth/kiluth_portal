"""Oracle: who gets notified for a Task event.

Runs without bench:  python -m unittest kiluth_portal.tests.test_task_notify_recipients
"""

import json
import unittest

from kiluth_portal.task_notify.recipients import (
	assignment_recipients,
	comment_recipients,
	parse_assign,
)

POOM = "poom.pengcharoen@kiluth.com"
REAW = "phuttipan.samranruen@kiluth.com"
SWARM = "swarm@kiluth.com"


def assign(*users):
	return json.dumps(list(users))


def todo(**kw):
	base = dict(reference_type="Task", allocated_to=POOM, actor=REAW, status="Open", is_new=True)
	base.update(kw)
	return assignment_recipients(**base)


def comment(**kw):
	base = dict(reference_doctype="Task", comment_type="Comment", commenter=REAW, task_assign_json=assign(POOM))
	base.update(kw)
	return comment_recipients(**base)


class Assignment(unittest.TestCase):
	def test_assignee_is_notified(self):
		self.assertEqual(todo(), [POOM])

	def test_self_assign_notifies_nobody(self):
		self.assertEqual(todo(actor=POOM), [])

	def test_actor_is_never_the_recipient(self):
		self.assertNotIn(REAW, todo())

	def test_self_assign_ignores_whitespace(self):
		self.assertEqual(todo(actor=f" {POOM} "), [])

	def test_non_task_todo_notifies_nobody(self):
		self.assertEqual(todo(reference_type="Issue"), [])
		self.assertEqual(todo(reference_type=None), [])

	def test_cancelled_or_closed_insert_notifies_nobody(self):
		self.assertEqual(todo(status="Cancelled"), [])
		self.assertEqual(todo(status="Closed"), [])

	def test_reopened_assignment_notifies(self):
		self.assertEqual(todo(is_new=False, old_status="Cancelled"), [POOM])

	def test_saving_an_open_todo_again_notifies_nobody(self):
		self.assertEqual(todo(is_new=False, old_status="Open"), [])

	def test_empty_assignee_notifies_nobody(self):
		self.assertEqual(todo(allocated_to=""), [])
		self.assertEqual(todo(allocated_to=None), [])

	def test_swarm_assigning_poom_notifies_poom(self):
		self.assertEqual(todo(actor=SWARM), [POOM])


class Comments(unittest.TestCase):
	def test_comment_by_other_notifies_assignee(self):
		self.assertEqual(comment(), [POOM])

	def test_commenter_is_not_notified(self):
		self.assertNotIn(REAW, comment(task_assign_json=assign(POOM, REAW)))

	def test_comment_by_assignee_notifies_nobody(self):
		self.assertEqual(comment(commenter=POOM), [])

	def test_comment_by_one_of_two_assignees_notifies_the_other(self):
		self.assertEqual(comment(commenter=POOM, task_assign_json=assign(POOM, REAW)), [REAW])

	def test_comment_on_unassigned_task_notifies_nobody(self):
		self.assertEqual(comment(task_assign_json=None), [])
		self.assertEqual(comment(task_assign_json="[]"), [])

	def test_non_human_comment_types_notify_nobody(self):
		for ct in ("Info", "Assigned", "Attachment", "Like", "Edit", "Label", "Workflow"):
			with self.subTest(ct=ct):
				self.assertEqual(comment(comment_type=ct), [])

	def test_comment_on_other_doctype_notifies_nobody(self):
		self.assertEqual(comment(reference_doctype="Issue"), [])

	def test_duplicate_assignees_notified_once(self):
		self.assertEqual(comment(task_assign_json=assign(POOM, POOM)), [POOM])

	def test_non_watchers_never_notified(self):
		# Someone who only follows or was mentioned is not an assignee: no push.
		self.assertEqual(comment(task_assign_json=assign(POOM)), [POOM])


class ParseAssign(unittest.TestCase):
	def test_garbage_is_empty(self):
		for raw in ("", None, "not json", "{}", "42", '[null, 3]'):
			with self.subTest(raw=raw):
				self.assertEqual(parse_assign(raw), [])

	def test_strips_blanks(self):
		self.assertEqual(parse_assign(assign(POOM, "", " ")), [POOM])


if __name__ == "__main__":
	unittest.main()
