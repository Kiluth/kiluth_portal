"""Checks for kiluth_portal/utils/task_chain.py. No Frappe needed:

	python3 kiluth_portal/tests/test_task_chain.py
"""

import importlib.util
import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("task_chain", os.path.join(here, "..", "utils", "task_chain.py"))
c = importlib.util.module_from_spec(spec)
sys.modules["task_chain"] = c
spec.loader.exec_module(c)


class TestLevels(unittest.TestCase):
	def test_straight_chain(self):
		self.assertEqual(c.levels(["a", "b", "c"], [("a", "b"), ("b", "c")]), {"a": 0, "b": 1, "c": 2})

	def test_longest_route_wins(self):
		links = [("a", "b"), ("b", "c"), ("a", "c")]
		self.assertEqual(c.levels(["a", "b", "c"], links)["c"], 2)

	def test_two_blockers_join(self):
		links = [("a", "c"), ("b", "c")]
		self.assertEqual(c.levels(["a", "b", "c"], links), {"a": 0, "b": 0, "c": 1})

	def test_loop_does_not_stop_the_page(self):
		out = c.levels(["a", "b"], [("a", "b"), ("b", "a")])
		self.assertEqual(set(out), {"a", "b"})


class TestThroughHidden(unittest.TestCase):
	def test_joins_across_a_hidden_task(self):
		self.assertEqual(c.through_hidden(["a", "c"], [("a", "b"), ("b", "c")]), [("a", "c")])

	def test_drops_links_to_hidden_ends(self):
		self.assertEqual(c.through_hidden(["a"], [("a", "b")]), [])

	def test_all_shown_is_unchanged(self):
		links = [("a", "b"), ("b", "c")]
		self.assertEqual(c.through_hidden(["a", "b", "c"], links), links)

	def test_loop_through_hidden_stops(self):
		self.assertEqual(c.through_hidden(["a"], [("a", "b"), ("b", "a")]), [])


class TestLayout(unittest.TestCase):
	def test_a_task_comes_after_its_blocker(self):
		out = c.layout(["c", "a", "b"], [("a", "b"), ("b", "c")])
		rows = {r["task"]: r["row"] for r in out["chain"]}
		self.assertLess(rows["a"], rows["b"])
		self.assertLess(rows["b"], rows["c"])

	def test_loose_tasks_stay_out_of_the_chain(self):
		out = c.layout(["a", "b", "z"], [("a", "b")])
		self.assertEqual(out["loose"], ["z"])
		self.assertEqual({r["task"] for r in out["chain"]}, {"a", "b"})

	def test_ends_are_tasks_that_block_nothing(self):
		out = c.layout(["a", "b", "c"], [("a", "b"), ("a", "c")])
		self.assertEqual(out["ends"], ["b", "c"])

	def test_every_row_is_used_once(self):
		links = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
		out = c.layout(["a", "b", "c", "d"], links)
		self.assertEqual(sorted(r["row"] for r in out["chain"]), [0, 1, 2, 3])

	def test_loop_is_still_placed(self):
		out = c.layout(["a", "b"], [("a", "b"), ("b", "a")])
		self.assertEqual(len(out["chain"]), 2)

	def test_no_links(self):
		out = c.layout(["a"], [])
		self.assertEqual((out["chain"], out["loose"]), ([], ["a"]))


if __name__ == "__main__":
	sys.exit(unittest.main())
