"""Delivery channels. A channel takes one outbox row and either returns or raises.

Add a channel: subclass Channel, give it a `name`, register it in CHANNELS.
Which channels run is set once for the whole site in site_config:
  "kiluth_notify_channels": ["log", "webpush"]   (["log"] when unset)
Nothing is configured per person on the server. "bell" always runs as well: it
is the in-app record the bell in the page head lists, not a way to reach a phone.
"""

import logging

logger = logging.getLogger("kiluth_portal.task_notify")


class Channel:
	name = ""

	def send(self, recipient, payload):
		raise NotImplementedError


class LogChannel(Channel):
	"""Writes the notification to the log. Proves the pipe without a phone."""

	name = "log"

	def send(self, recipient, payload):
		logger.info("task_notify -> %s: %s | %s | %s", recipient, payload.get("title"), payload.get("body"), payload.get("url"))


class WebPushChannel(Channel):
	"""Phone and browser push (VAPID + pywebpush) to every device the person turned on."""

	name = "webpush"

	def send(self, recipient, payload):
		from kiluth_portal.web_push.sender import send_to_user

		send_to_user(recipient, payload)


class BellChannel(Channel):
	"""A Notification Log row, so a notification can be found again after it's gone
	from the phone. The desk writes its own row for an assignment, so only comments."""

	name = "bell"

	def send(self, recipient, payload):
		if payload.get("kind") != "task.commented":
			return
		import frappe
		from frappe.utils import escape_html

		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"type": "Alert",  # the desk sends no email for an Alert
				"for_user": recipient,
				"document_type": "Task",
				"document_name": payload["task"],
				"subject": escape_html(payload.get("title") or ""),
				"email_content": escape_html(payload.get("body") or ""),
			}
		).insert(ignore_permissions=True)


class ExpoChannel(Channel):
	"""Stub. Real version: POST to Expo's push API with the user's Expo push token(s)."""

	name = "expo"


CHANNELS = {c.name: c for c in (LogChannel, WebPushChannel, BellChannel, ExpoChannel)}
DEFAULT_CHANNELS = ("log",)
ALWAYS = ("bell",)


def enabled(names=None):
	"""Channel instances for the configured names, then the ones that always run. Unknown names are skipped."""
	names = list(names or DEFAULT_CHANNELS)
	names += [n for n in ALWAYS if n not in names]
	return [CHANNELS[n]() for n in names if n in CHANNELS]
