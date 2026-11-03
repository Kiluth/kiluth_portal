"""Tasks the website makes have a project, and their assignee can close them.
LOCAL THROWAWAY bench only: makes made-up customers, projects and tasks, then deletes them.

	bench --site notify.localhost execute kiluth_portal.tests.bench_website_tasks.run
"""

import frappe

from kiluth_portal.api import client_brief, website_lead
from kiluth_portal.utils import lead_routing

SALES, OTHER, ADMIN = "e2e-sales@kiluth.com", "e2e-member@kiluth.com", "e2e-assigner@kiluth.com"
BOT = website_lead.BOT_USER


def _set(name, user, **fields):
	frappe.set_user(user)
	frappe.clear_messages()
	try:
		doc = frappe.get_doc("Task", name)
		doc.update(fields)
		doc.save(ignore_permissions=True)
		return None
	except frappe.ValidationError as e:
		return str(e)
	finally:
		frappe.set_user("Administrator")


def _customer(name, projects):
	frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company",
	                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
	                "territory": frappe.db.get_value("Territory", {"is_group": 0}),
	                "custom_unique_email_id": f"{name.lower().replace(' ', '-')}@e2e.local"}).insert(ignore_permissions=True)
	made = []
	for i in range(projects):
		# Inserted directly: the bench has no Company, which a Project needs.
		p = frappe.new_doc("Project")
		p.name, p.project_name, p.customer, p.status = f"E2E-{name[:12]}-{i}", f"{name} {i}", name, "Open"
		p.db_insert()
		made.append(p.name)
	return made


def run():
	frappe.set_user("Administrator")
	out, tasks, customers, projects = [], [], [], []
	made_bot = not frappe.db.exists("User", BOT)
	if made_bot:
		frappe.get_doc({"doctype": "User", "email": BOT, "first_name": "Website", "send_welcome_email": 0,
		                "user_type": "System User"}).insert(ignore_permissions=True)
	# Live has this department; the bench has no company to make it from.
	made_dept = not frappe.db.exists("Department", "Account Management - K")
	if made_dept:
		dept = frappe.new_doc("Department")
		dept.name = dept.department_name = "Account Management - K"
		dept.db_insert()
	# ERPNext re-saves the project after a task save; on the bench projects have no Company.
	from erpnext.projects.doctype.task.task import Task
	real_update = Task.update_project
	Task.update_project = lambda self: None
	real = client_brief.pick_salesperson, lead_routing.pick_salesperson
	client_brief.pick_salesperson = lead_routing.pick_salesperson = lambda: SALES
	try:
		frappe.set_user(BOT)
		with_code = client_brief._link_task("E2E Brief Co", "PROJ-0015", False)
		no_code = client_brief._link_task("E2E Brief Two", "", False)
		frappe.set_user("Administrator")
		tasks += [with_code, no_code]
		get = lambda t, f: frappe.db.get_value("Task", t, f)
		out.append(("brief with a valid code: on Operations, not on the typed project",
		            get(with_code, "project") == "PROJ-0001", get(with_code, "project")))
		out.append(("brief with a code: the code is still a hint in the description",
		            "PROJ-0015" in (get(with_code, "description") or ""), None))
		out.append(("brief with no code: on Operations", get(no_code, "project") == "PROJ-0001", get(no_code, "project")))

		for name, n in (("E2E One Project Co", 1), ("E2E Two Projects Co", 2)):
			customers.append(name)
			projects += _customer(name, n)
		frappe.set_user(BOT)
		website_lead._client_message("E2E One Project Co", "Can you change the opening hours?")
		website_lead._client_message("E2E Two Projects Co", "A question about the invoice.")
		frappe.set_user("Administrator")
		one = frappe.db.get_value("Task", {"subject": "Client message: E2E One Project Co"}, ["name", "project"], as_dict=True)
		two = frappe.db.get_value("Task", {"subject": "Client message: E2E Two Projects Co"}, ["name", "project"], as_dict=True)
		tasks += [one.name, two.name]
		out.append(("client message, one open project: on that project", one.project == projects[0], one.project))
		out.append(("client message, two open projects: on Operations", two.project == "PROJ-0001", two.project))
		out.append(("every website task has a project (check rule 5 passes)",
		            all(frappe.db.get_value("Task", t, "project") for t in tasks), None))

		# Nobody asked for these: whoever has them closes them.
		msg = _set(with_code, OTHER, status="Completed")
		out.append(("someone not on it is refused",
		            msg == "Only its assignee or an admin can complete this. Set it to Pending Review so they can check it.", msg))
		out.append(("its assignee completes it", _set(with_code, SALES, status="Completed") is None,
		            frappe.db.get_value("Task", with_code, ["status", "completed_by"])))
		out.append(("an admin completes one", _set(no_code, ADMIN, status="Completed") is None, None))
		lead_routing.move(one.name, "Client message: E2E One Project Co", OTHER)
		out.append(("after it moves on, the first assignee no longer can", _set(one.name, SALES, status="Completed") is not None,
		            frappe.db.get_value("Task", one.name, "_assign")))
		out.append(("and the new assignee completes it", _set(one.name, OTHER, status="Completed") is None,
		            frappe.db.get_value("Task", one.name, "_assign")))
	finally:
		client_brief.pick_salesperson, lead_routing.pick_salesperson = real
		Task.update_project = real_update
		frappe.set_user("Administrator")
		for t in tasks:
			for dt, key in (("Comment", "reference_name"), ("ToDo", "reference_name"), ("Version", "docname")):
				frappe.db.delete(dt, {key: t})
			frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
		for p in projects:
			frappe.db.delete("Project", {"name": p})
		for c in customers:
			frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": c})
			frappe.delete_doc("Customer", c, force=True, ignore_permissions=True)
		if made_bot:
			frappe.delete_doc("User", BOT, force=True, ignore_permissions=True)
		if made_dept:
			frappe.db.delete("Department", {"name": "Account Management - K"})
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(ok for _, ok, _ in out)}/{len(out)}")
