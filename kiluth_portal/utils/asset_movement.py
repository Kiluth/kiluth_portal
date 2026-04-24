"""Asset Movement sync for Equipment Loan Agreement / Equipment Return.

Wired via `doc_events` on_submit. Keeps `Asset.custodian` accurate so
"who has what" reporting works against native ERPNext Asset views.
"""

import frappe


def sync_on_loan(doc, method=None):
	"""Move each loaned asset's custody to the borrower."""
	for row in doc.assets:
		_create_movement(
			asset=row.asset,
			to_employee=doc.employee,
			purpose="Issue",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)


def sync_on_return(doc, method=None):
	"""Move each returned asset's custody back to the default storage location."""
	storage_location = _default_storage_location()

	for row in doc.assets_returned:
		_create_movement(
			asset=row.asset,
			to_location=storage_location,
			purpose="Receipt",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)


def _create_movement(
	asset,
	purpose,
	reference_doctype,
	reference_name,
	to_employee=None,
	to_location=None,
):
	asset_doc = frappe.get_doc("Asset", asset)

	movement = frappe.get_doc(
		{
			"doctype": "Asset Movement",
			"purpose": purpose,
			"company": asset_doc.company,
			"transaction_date": frappe.utils.now_datetime(),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"assets": [
				{
					"asset": asset,
					"source_location": asset_doc.location,
					"from_employee": asset_doc.custodian,
					"to_employee": to_employee,
					"target_location": to_location,
				}
			],
		}
	)
	movement.flags.ignore_permissions = True
	movement.insert()
	movement.submit()


def _default_storage_location():
	location = frappe.db.get_single_value("HR Settings", "default_asset_storage_location")
	if location:
		return location

	return frappe.db.get_value("Location", {"location_name": "Kiluth HQ Storage"}, "name")
