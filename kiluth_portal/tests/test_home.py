import json
import unittest
from urllib.parse import parse_qs, urlparse

from kiluth_portal.utils.home import task_board_url, task_list_url


class TestTaskBoardUrl(unittest.TestCase):
	def test_filters_board_to_user(self):
		url = urlparse(task_board_url("poom.pengcharoen@kiluth.com"))
		self.assertEqual(url.path, "/desk/task/view/kanban/Tasks")
		self.assertEqual(json.loads(parse_qs(url.query)["_assign"][0]), ["like", "%poom.pengcharoen@kiluth.com%"])


class TestTaskListUrl(unittest.TestCase):
	def test_filters_task_list_to_user(self):
		url = urlparse(task_list_url("poom.pengcharoen@kiluth.com"))
		self.assertEqual(url.path, "/desk/task")
		value = parse_qs(url.query)["_assign"][0]
		self.assertEqual(json.loads(value), ["like", "%poom.pengcharoen@kiluth.com%"])

	def test_value_is_fully_encoded(self):
		self.assertNotIn("@", task_list_url("a@kiluth.com").split("?", 1)[1])
