"""Delivery channels. A channel takes one outbox row and either returns or raises.

Add a channel: subclass Channel, give it a `name`, register it in CHANNELS.
Which channels run is set once for the whole site in site_config:
  "kiluth_notify_channels": ["log", "webpush"]   (["log"] when unset)
Nothing is configured per person on the server.
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


class ExpoChannel(Channel):
	"""Stub. Real version: POST to Expo's push API with the user's Expo push token(s)."""

	name = "expo"


CHANNELS = {c.name: c for c in (LogChannel, WebPushChannel, ExpoChannel)}
DEFAULT_CHANNELS = ("log",)


def enabled(names=None):
	"""Channel instances for the configured names. Unknown names are skipped."""
	return [CHANNELS[n]() for n in (names or DEFAULT_CHANNELS) if n in CHANNELS]
