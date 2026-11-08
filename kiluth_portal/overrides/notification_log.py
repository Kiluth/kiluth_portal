"""People-only notifications on the desk's own Notification Log rows.

Frappe writes a Notification Log row for every assignment, removal and
mention, and emails each one (frappe/desk/doctype/notification_log). For a
user listed in `kiluth_people_only_notify` (task_notify/quiet.py):

  - "your assignment was removed" rows are not written at all
  - every other row is written as usual, so the bell and Hub still see it,
    but sends no email; task_notify/digest.py sends one summary a day

Nothing changes for anyone not listed.
"""

import frappe
from frappe.desk.doctype.notification_log.notification_log import NotificationLog, set_notifications_as_unseen

from kiluth_portal.task_notify import quiet


class KiluthNotificationLog(NotificationLog):
	def insert(self, *args, **kwargs):
		people_only, _ = quiet.settings(frappe.conf)
		if quiet.drop_log(for_user=self.for_user, log_type=self.type, subject=self.subject, people_only=people_only):
			return self
		return super().insert(*args, **kwargs)

	def after_insert(self):
		people_only, _ = quiet.settings(frappe.conf)
		if quiet.email_log(for_user=self.for_user, people_only=people_only):
			return super().after_insert()
		# Frappe's after_insert without the email.
		frappe.publish_realtime("notification", after_commit=True, user=self.for_user)
		set_notifications_as_unseen(self.for_user)
