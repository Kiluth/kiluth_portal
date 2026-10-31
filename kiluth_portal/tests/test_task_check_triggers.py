"""Checks for kiluth_portal/task_check/triggers.py. No Frappe needed:

	python3 kiluth_portal/tests/test_task_check_triggers.py
"""

import importlib.util
import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("triggers", os.path.join(here, "..", "task_check", "triggers.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class Row:
	def __init__(self, task):
		self.task = task


def state(**over):
	base = {"subject": "Fix it", "description": "Done when fixed", "status": "Open", "depends_on": ["TASK-1"]}
	return {**base, **over}


class TestTaskChanged(unittest.TestCase):
	def test_new_task_runs(self):
		self.assertTrue(t.task_changed(None, state()))

	def test_title_runs(self):
		self.assertTrue(t.task_changed(state(), state(subject="Fix it now")))

	def test_description_runs(self):
		self.assertTrue(t.task_changed(state(), state(description="Done when it passes")))

	def test_status_runs(self):
		self.assertTrue(t.task_changed(state(), state(status="Pending Review")))

	def test_dependency_added_or_removed_runs(self):
		self.assertTrue(t.task_changed(state(), state(depends_on=["TASK-1", "TASK-2"])))
		self.assertTrue(t.task_changed(state(), state(depends_on=[])))

	def test_nothing_else_runs(self):
		self.assertFalse(t.task_changed(state(), state()))

	def test_checker_fields_and_the_rest_do_not_run(self):
		noisy = state(hygiene="Pass", hygiene_note="x", project="PROJ-0001", priority="High", modified="now")
		self.assertFalse(t.task_changed(state(), noisy))

	def test_blank_and_none_are_the_same(self):
		self.assertFalse(t.task_changed(state(description=""), state(description=None)))


class TestTaskState(unittest.TestCase):
	def test_dependency_order_does_not_matter(self):
		a = {"subject": "s", "description": "d", "status": "Open", "depends_on": [Row("B"), Row("A")]}
		b = {"subject": "s", "description": "d", "status": "Open", "depends_on": [Row("A"), Row("B")]}
		self.assertEqual(t.task_state(a), t.task_state(b))

	def test_only_listed_fields(self):
		self.assertEqual(set(t.task_state({"subject": "s", "hygiene": "Pass"})), set(t.TASK_FIELDS))


class TestAssigneeChanged(unittest.TestCase):
	def test_new_assignment_runs(self):
		self.assertTrue(t.assignee_changed("Task", None, "Open"))

	def test_removed_or_closed_runs(self):
		self.assertTrue(t.assignee_changed("Task", "Open", "Cancelled"))
		self.assertTrue(t.assignee_changed("Task", "Open", "Closed"))

	def test_reopened_runs(self):
		self.assertTrue(t.assignee_changed("Task", "Cancelled", "Open"))

	def test_same_status_does_not_run(self):
		self.assertFalse(t.assignee_changed("Task", "Open", "Open"))
		self.assertFalse(t.assignee_changed("Task", "Closed", "Cancelled"))

	def test_other_doctypes_do_not_run(self):
		self.assertFalse(t.assignee_changed("Lead", None, "Open"))


if __name__ == "__main__":
	sys.exit(unittest.main())
