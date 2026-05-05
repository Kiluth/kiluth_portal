"""Idempotent per-doctype default Print Format wiring.

Frappe's "Default Print Format" is set via Customize Form, which creates a
Property Setter against the doctype itself. We can't ship that as a normal
Property Setter fixture because the host doctype (Quotation, Sales Invoice,
Payment Entry) belongs to ERPNext's Selling/Accounts modules, not a Kiluth
module — so the existing fixture filter (module IN KILUTH_MODULES) skips it.

Hooked into `after_migrate`, this runs after the kiluth_portal Print Format
fixtures have already loaded, so the target Print Formats are guaranteed to
exist. Each call is idempotent — only writes when the current value differs.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

DEFAULT_PRINT_FORMATS = {
	"Quotation": "Quotation Print",
	"Sales Invoice": "Invoice Print",
	"Payment Entry": "Receipt",
}


def apply_default_print_formats():
	for doctype, print_format in DEFAULT_PRINT_FORMATS.items():
		# Defensive: if the Print Format hasn't loaded (or was renamed),
		# leave the default alone rather than pointing at something missing.
		if not frappe.db.exists("Print Format", print_format):
			print(f"[kiluth_portal] Skipping {doctype} default — Print Format {print_format!r} not found")
			continue
		current = frappe.db.get_value(
			"Property Setter",
			{"doc_type": doctype, "property": "default_print_format"},
			"value",
		)
		if current == print_format:
			continue
		make_property_setter(
			doctype=doctype,
			fieldname=None,
			property="default_print_format",
			value=print_format,
			property_type="Data",
			for_doctype=True,
		)
		print(f"[kiluth_portal] Default Print Format on {doctype}: {current!r} -> {print_format!r}")
