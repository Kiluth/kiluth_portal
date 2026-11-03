"""Who a task's requester is, and who may complete a task.

The requester is the task's creator. Tasks a system created have no requester:
the task check (kiluth-infra modules/task-check/lambda/check_tasks.py) leaves
them out of its requester rule, and this list must match its NO_REQUESTER, so
the Portal and the check never disagree about whose task it is.

Only the requester, or an admin, completes a task (Poom, 2026-11-03; docs.kiluth.com
/delivery/working-with-tasks). Everyone else finishes by setting Pending Review,
which hands the task back. A task with no requester, such as one the website
or Kiluth Swarm made, is completed by whoever it is assigned to, or an admin:
nobody else asked for it, and its assignee can change (a lead is escalated).
"""
import frappe

NO_REQUESTER = frozenset({"Administrator", "Guest", "swarm@kiluth.com", "website-bot@kiluth.com"})
ADMIN_ROLE = "System Manager"


def requester_of(owner):
	"""The task's requester, or None when a system created it."""
	owner = (owner or "").strip()
	return None if not owner or owner in NO_REQUESTER else owner


def is_admin(user):
	return user == "Administrator" or ADMIN_ROLE in frappe.get_roles(user)


def may_complete(user, owner, assignees=()):
	requester = requester_of(owner)
	if requester is None and user in assignees:
		return True
	return user == requester or is_admin(user)
