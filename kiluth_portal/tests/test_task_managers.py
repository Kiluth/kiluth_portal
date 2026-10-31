"""Run where Frappe is installed: python -m unittest kiluth_portal.tests.test_task_managers"""

import unittest

from kiluth_portal.utils.task_managers import to_copy


class TestToCopy(unittest.TestCase):
	def test_fills_blanks(self):
		got = to_copy({}, {"account_manager": "a", "project_manager": "p"})
		self.assertEqual(got, {"account_manager": "a", "project_manager": "p"})

	def test_a_name_already_there_stays(self):
		got = to_copy({"account_manager": "me"}, {"account_manager": "a", "project_manager": "p"})
		self.assertEqual(got, {"project_manager": "p"})

	def test_a_blank_on_the_project_copies_nothing(self):
		self.assertEqual(to_copy({}, {"account_manager": None, "project_manager": ""}), {})
		self.assertEqual(to_copy({}, {}), {})
