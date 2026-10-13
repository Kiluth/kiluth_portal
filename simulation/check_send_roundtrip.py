"""Spike check: pywebpush encrypts our payload so a real browser could read it.

Plays the browser: makes a P-256 keypair + auth secret, hands them to
webpush() as a subscription, captures the HTTP request instead of sending it,
then decrypts the body with the browser's private key. No network used.

Run: python simulation/check_send_roundtrip.py  (needs pywebpush installed)
"""

import base64
import json
import os
from unittest import mock

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid
from pywebpush import webpush


def b64u(b):
	return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


# Server side: VAPID keys as they would sit in site_config.
vapid = Vapid()
vapid.generate_keys()
priv_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
pub_raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
site_config = {"kiluth_vapid_private_key": b64u(priv_raw), "kiluth_vapid_public_key": b64u(pub_raw)}

# Browser side: what pushManager.subscribe() returns.
ua_key = ec.generate_private_key(ec.SECP256R1())
ua_pub = ua_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
auth = os.urandom(16)
sub = {"endpoint": "https://web.push.apple.com/QFAKE", "keys": {"p256dh": b64u(ua_pub), "auth": b64u(auth)}}

payload = {"title": "Reaw assigned you a task", "body": "Check the invoice", "url": "/app/task/TASK-2026-00001", "tag": "task-TASK-2026-00001"}
captured = {}


def fake_post(url, data=None, headers=None, timeout=None, **kw):
	captured.update(url=url, data=data, headers=headers)
	return mock.Mock(status_code=201, text="")


with mock.patch("requests.post", fake_post):
	webpush(
		subscription_info=sub,
		data=json.dumps(payload),
		vapid_private_key=site_config["kiluth_vapid_private_key"],
		vapid_claims={"sub": "mailto:technology@kiluth.com"},
		ttl=86400,
	)

plain = http_ece.decrypt(captured["data"], private_key=ua_key, auth_secret=auth, version="aes128gcm")
assert json.loads(plain) == payload, plain
assert captured["url"] == sub["endpoint"]
assert captured["headers"]["Authorization"].startswith("vapid t="), captured["headers"]
assert captured["headers"]["ttl"] == "86400"
print("OK — payload decrypts on the 'browser' side; VAPID header:", captured["headers"]["Authorization"][:40] + "...")
print("site_config keys:", {k: len(v) for k, v in site_config.items()})
