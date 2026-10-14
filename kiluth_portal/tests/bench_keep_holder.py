import json
import frappe
from frappe.desk.form.assign_to import add


def _assignees(name):
	return json.loads(frappe.db.get_value("Task", name, "_assign") or "[]")


def run():
	frappe.set_user("Administrator")
	out = {}
	proj = frappe.get_all("Project", limit=1, pluck="name")
	t = frappe.get_doc({"doctype": "Task", "subject": "Holder test: keep the name on completion",
		"project": proj[0] if proj else None, "status": "Open"}).insert()
	add({"doctype": "Task", "name": t.name, "assign_to": ["e2e-assignee@kiluth.com"]})
	out["before"] = _assignees(t.name)
	t.reload(); t.status = "Completed"; t.save()
	out["after_complete"] = _assignees(t.name)
	t.reload(); t.description = "edited after completion"; t.save()
	out["after_edit"] = _assignees(t.name)
	c = frappe.get_doc({"doctype": "Task", "subject": "Holder test: cancel clears", "status": "Open",
		"project": proj[0] if proj else None}).insert()
	add({"doctype": "Task", "name": c.name, "assign_to": ["e2e-assignee@kiluth.com"]})
	c.reload(); c.status = "Cancelled"; c.save()
	out["cancelled"] = _assignees(c.name)
	d = frappe.get_doc({"doctype": "Task", "subject": "Holder test: blocked cannot complete", "status": "Open",
		"project": proj[0] if proj else None, "depends_on": [{"task": c.name}]}).insert()
	b = frappe.get_doc({"doctype": "Task", "subject": "Holder test: open blocker", "status": "Open",
		"project": proj[0] if proj else None}).insert()
	d.append("depends_on", {"task": b.name}); d.save()
	try:
		d.reload(); d.status = "Completed"; d.save(); out["dependency_check"] = "NOT ENFORCED"
	except frappe.ValidationError:
		out["dependency_check"] = "still enforced"
	frappe.db.rollback()
	print(json.dumps(out))
