"""Sales (the Commercial role) makes a project from a Sales Order, on a LOCAL THROWAWAY
bench. Makes up a company, customer, Sales Order, user, project and task, then deletes
them. Never run this against portal.kiluth.com.

	bench --site notify.localhost execute kiluth_portal.tests.bench_commercial_projects.run
"""

import frappe

SALES = "e2e-commercial-only@kiluth.com"
AE = "e2e-sales@kiluth.com"
COMPANY, CUSTOMER = "E2E Commercial Co", "E2E Commercial Client"


def _as(user, fn):
	frappe.set_user(user)
	frappe.clear_messages()
	try:
		return fn(), None
	except (frappe.PermissionError, frappe.ValidationError) as e:
		return None, f"{type(e).__name__}: {e}"
	finally:
		frappe.set_user("Administrator")


def run():
	frappe.set_user("Administrator")
	out, made = [], {"Project": [], "Task": []}
	so_name, made_type = None, False
	# ERPNext re-saves the project after a task save, which needs a full company setup.
	from erpnext.projects.doctype.task.task import Task
	real_update = Task.update_project
	Task.update_project = lambda self: None
	try:
		# The bench has no Company; a bare record is enough for the links.
		c = frappe.new_doc("Company")
		c.name = c.company_name = COMPANY
		c.abbr, c.default_currency, c.country = "E2EC", "THB", "Thailand"
		c.db_insert()
		# The bench's PROJ- counter lags projects made with set names; live's doesn't. Move it past them.
		top = max([int(n[5:]) for n in frappe.get_all("Project", pluck="name") if n[:5] == "PROJ-" and n[5:].isdigit()] or [0])
		frappe.db.sql("insert into `tabSeries` (name, current) values ('PROJ-', %s) on duplicate key update current = greatest(current, %s)", (top, top))
		# Live has the standard Project Types; the bench may not. Create → Project sets "External".
		made_type = not frappe.db.exists("Project Type", "External")
		if made_type:
			frappe.get_doc({"doctype": "Project Type", "project_type": "External"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
		                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
		                "territory": frappe.db.get_value("Territory", {"is_group": 0}),
		                "custom_unique_email_id": "e2e-commercial-client@e2e.local"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", SALES):
			frappe.get_doc({"doctype": "User", "email": SALES, "first_name": "Cee Commercial", "send_welcome_email": 0,
			                "user_type": "System User", "roles": [{"role": "Commercial"}]}).insert(ignore_permissions=True)
		out.append(("the test user has Commercial and nothing that grants projects",
		            set(frappe.get_roles(SALES)) - {"All", "Guest", "Desk User"} == {"Commercial"}, frappe.get_roles(SALES)))

		# A submitted Sales Order, written directly: a real submit needs stock and accounts setup.
		so = frappe.new_doc("Sales Order")
		so.update({"customer": CUSTOMER, "company": COMPANY, "transaction_date": "2026-11-05", "delivery_date": "2026-12-31",
		           "currency": "THB", "conversion_rate": 1, "selling_price_list": "Standard Selling", "price_list_currency": "THB",
		           "plc_conversion_rate": 1, "base_grand_total": 100000, "grand_total": 100000, "net_total": 100000,
		           "base_net_total": 100000, "per_delivered": 0, "docstatus": 1, "status": "To Deliver and Bill"})
		so.set_new_name()
		so.db_insert()
		so_name = so.name

		out.append(("Commercial can create a Project", frappe.has_permission("Project", "create", user=SALES), None))
		out.append(("Commercial still can't delete a Project", not frappe.has_permission("Project", "delete", user=SALES), None))

		from erpnext.selling.doctype.sales_order.sales_order import make_project

		def create():
			doc = make_project(so_name)
			named_after_order = doc.project_name == so_name
			doc.project_name = "E2E Commercial Client Website"
			doc.account_manager = AE
			doc.insert()
			return doc.name, named_after_order
		res, err = _as(SALES, create)
		proj = res[0] if res else None
		if proj:
			made["Project"].append(proj)
		out.append(("Commercial makes a Project from the submitted Sales Order (Create → Project)", proj is not None, err))
		if proj:
			p = frappe.db.get_value("Project", proj, ["project_name", "customer", "sales_order", "company", "account_manager", "project_type", "owner"], as_dict=True)
			out.append(("ERPNext names it after the Sales Order until Sales renames it", res[1], None))
			out.append(("it carries the customer, company and Sales Order", (p.customer, p.company, p.sales_order) == (CUSTOMER, COMPANY, so_name), p))
			out.append(("renamed and Account Manager set in the same step", (p.project_name, p.account_manager) == ("E2E Commercial Client Website", AE), p))
			out.append(("it gets a code from the naming series, not a typed one", proj.startswith("PROJ-"), proj))

			def edit():
				doc = frappe.get_doc("Project", proj)
				doc.project_name = "E2E Commercial Client Website v2"
				doc.save()
			_, err = _as(SALES, edit)
			out.append(("Commercial can edit the project afterwards", err is None, err))
			_, err = _as(SALES, lambda: frappe.delete_doc("Project", proj))
			out.append(("Commercial is refused when deleting it", err is not None and "PermissionError" in err, err))

			# What the rest of the Portal does with a project made this way.
			t = frappe.get_doc({"doctype": "Task", "subject": "E2E task on the Sales-made project", "status": "Open",
			                    "project": proj}).insert(ignore_permissions=True)
			made["Task"].append(t.name)
			tv = frappe.db.get_value("Task", t.name, ["customer", "account_manager"], as_dict=True)
			out.append(("a task on it gets the Customer (Task Customer)", tv.customer == CUSTOMER, tv))
			out.append(("a task on it gets the AE (manager copy)", tv.account_manager == AE, tv))
	finally:
		Task.update_project = real_update
		frappe.set_user("Administrator")
		for t in made["Task"]:
			for dt, key in (("Comment", "reference_name"), ("ToDo", "reference_name"), ("Version", "docname")):
				frappe.db.delete(dt, {key: t})
			frappe.db.delete("Task", {"name": t})
		for p in made["Project"]:
			frappe.db.delete("Version", {"ref_doctype": "Project", "docname": p})
			frappe.db.delete("Comment", {"reference_doctype": "Project", "reference_name": p})
			frappe.db.delete("Project", {"name": p})
		if so_name:
			frappe.db.delete("Sales Order", {"name": so_name})
		frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": CUSTOMER})
		frappe.db.delete("Customer", {"name": CUSTOMER})
		frappe.db.delete("Company", {"name": COMPANY})
		if made_type:
			frappe.db.delete("Project Type", {"name": "External"})
		if frappe.db.exists("User", SALES):
			frappe.delete_doc("User", SALES, force=True, ignore_permissions=True)
		frappe.db.commit()

	for label, ok, seen in out:
		print(("ok  " if ok else "FAIL") + " " + label + ("" if ok else f"  {seen}"))
	print(f"{sum(bool(ok) for _, ok, _ in out)}/{len(out)}")
