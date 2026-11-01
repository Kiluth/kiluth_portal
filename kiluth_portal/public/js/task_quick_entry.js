// Add task (Poom, 2026-11-01): what a task needs to be ready to work on, in one
// short form. Assignee goes through hand-over, so a task still has one owner.
// "Done when" is a line in the description, by house rule.
frappe.provide("frappe.ui.form");

frappe.ui.form.TaskQuickEntryForm = class TaskQuickEntryForm extends frappe.ui.form.QuickEntryForm {
	set_meta_and_mandatory_fields() {
		super.set_meta_and_mandatory_fields();
		this.docfields = [
			{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1 },
			{ fieldname: "project", fieldtype: "Link", options: "Project", label: __("Project") },
			{
				fieldname: "assignee", fieldtype: "Link", options: "User", label: __("Assignee"), default: frappe.session.user,
				get_query: () => ({ filters: { enabled: 1, user_type: "System User" } }),
			},
			{ fieldname: "due", fieldtype: "Date", label: __("Due") }, // named so the form doesn't take the Task field's label
			{ fieldname: "done_when", fieldtype: "Small Text", label: __("Done when"), max_height: "96px" },
		];
	}

	render_dialog() {
		super.render_dialog();
		// iPhones zoom the page when a field under 16px takes focus.
		this.$wrapper.find(".form-control").css("font-size", "16px");
	}

	update_doc() {
		const doc = super.update_doc();
		this.assignee = doc.assignee;
		delete doc.assignee;
		if (doc.due) doc.exp_end_date = doc.due;
		delete doc.due;
		const done = (doc.done_when || "").trim().replace(/\s+/g, " ");
		delete doc.done_when;
		if (done) doc.description = `<p>${__("Done when")}: ${frappe.utils.escape_html(done)}</p>`;
		return doc;
	}

	// The desk's own insert, less its Submit step: it treats managers as able to submit
	// a Task, which can't be submitted, and then never finishes the insert.
	insert() {
		return new Promise((resolve) => {
			this.update_doc();
			frappe.call({
				method: "frappe.client.save",
				args: { doc: this.doc },
				callback: (r) => {
					this.process_after_insert(r);
					resolve(this.doc);
				},
				error: () => this.open_doc(true),
				always: () => (this.working = false),
			});
		});
	}

	process_after_insert(r) {
		super.process_after_insert(r);
		if (!this.assignee) return;
		frappe.xcall("kiluth_portal.utils.task_page.hand_over", { task: this.doc.name, to_user: this.assignee }).then(
			() => window.cur_list?.doctype === "Task" && cur_list.refresh(),
			() => frappe.show_alert({ message: __("Task added, but not assigned"), indicator: "orange" })
		);
	}
};
