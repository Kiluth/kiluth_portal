import json
import unittest
from urllib.parse import parse_qs, urlparse

from kiluth_portal.utils.home import task_board_url


class TestTaskBoardUrl(unittest.TestCase):
	def test_filters_board_to_user(self):
		url = urlparse(task_board_url("poom.pengcharoen@kiluth.com"))
		self.assertEqual(url.path, "/desk/task/view/kanban/Tasks")
		self.assertEqual(json.loads(parse_qs(url.query)["_assign"][0]), ["like", "%poom.pengcharoen@kiluth.com%"])

	def test_value_is_fully_encoded(self):
		self.assertNotIn("@", task_board_url("a@kiluth.com").split("?", 1)[1])

	def test_both_addresses_open_the_board(self):
		from kiluth_portal.utils.home import BOARD_PATH, HOME_PATH, MyTasksRedirect

		self.assertIs(MyTasksRedirect.TARGETS[HOME_PATH], task_board_url)
		self.assertIs(MyTasksRedirect.TARGETS[BOARD_PATH], task_board_url)
