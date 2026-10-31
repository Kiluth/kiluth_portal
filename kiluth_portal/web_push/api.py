"""Endpoints the desk calls to turn phone notifications on/off for the current user."""

import frappe

from kiluth_portal.web_push.sender import DOCTYPE, send_to_user


@frappe.whitelist()
def get_vapid_public_key():
	return frappe.conf.get("kiluth_vapid_public_key")


@frappe.whitelist(methods=["POST"])
def subscribe(endpoint, p256dh, auth, user_agent=None):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Login required", frappe.PermissionError)
	existing = frappe.db.get_value(DOCTYPE, {"endpoint": endpoint}, "name")
	doc = frappe.get_doc(DOCTYPE, existing) if existing else frappe.new_doc(DOCTYPE)
	doc.update({"user": user, "endpoint": endpoint, "p256dh": p256dh, "auth": auth, "user_agent": (user_agent or "")[:140]})
	doc.save(ignore_permissions=True)
	return "ok"


@frappe.whitelist(methods=["POST"])
def unsubscribe(endpoint):
	name = frappe.db.get_value(DOCTYPE, {"endpoint": endpoint, "user": frappe.session.user}, "name")
	if name:
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)
	return "ok"


@frappe.whitelist(methods=["POST"])
def send_test():
	send_to_user(
		frappe.session.user,
		{"title": "Kiluth Portal", "body": "Phone notifications are on.", "url": "/app/todo", "tag": "kiluth-test"},
	)
	return "ok"
