"""Checks for kiluth_portal/utils/task_titles.py. No Frappe needed:

	python3 kiluth_portal/tests/test_task_titles.py
"""

import importlib.util
import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("task_titles", os.path.join(here, "..", "utils", "task_titles.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class TestBare(unittest.TestCase):
	def test_removes_the_prefix(self):
		self.assertEqual(t.bare("[Finance] Close the books for October 2026"), "Close the books for October 2026")

	def test_two_word_department(self):
		self.assertEqual(t.bare("[Human Resource] Run the awards"), "Run the awards")

	def test_no_prefix_is_unchanged(self):
		self.assertEqual(t.bare("Close the books for October 2026"), "Close the books for October 2026")

	def test_only_a_leading_bracket_counts(self):
		self.assertEqual(t.bare("Fix [Elyscel] pixels"), "Fix [Elyscel] pixels")

	def test_blank(self):
		self.assertEqual(t.bare(None), "")


class TestWithDepartment(unittest.TestCase):
	def test_drops_the_company_suffix(self):
		self.assertEqual(t.with_department("Book it", "Finance - K"), "[Finance] Book it")

	def test_two_words(self):
		self.assertEqual(t.with_department("Run it", "Account Management - K"), "[Account Management] Run it")

	def test_never_doubles(self):
		self.assertEqual(t.with_department("[Finance] Book it", "Finance - K"), "[Finance] Book it")

	def test_no_department_leaves_it(self):
		self.assertEqual(t.with_department("Book it", None), "Book it")


if __name__ == "__main__":
	sys.exit(unittest.main())
