"""Seed which suppliers attract Thai 3% withholding.

Runs once, after `custom_withhold_3pct` and `custom_withholding_reviewed`
exist on Supplier. The Portal's own fields can't decide this — every supplier
here is country Thailand, including Google and AWS — so it was decided by hand
from what each supplier was actually paid for (Finance, 2026-10-24).

Only these suppliers are touched. Anything else stays unreviewed, so the
monthly withholding check reports it rather than guessing. A supplier added
later is classified on its own record.
"""

import frappe

# Thai service providers: paying them for a service means withholding 3%.
WITHHOLD = [
	"Freelance Labor",  # freelancers, e.g. design work
	"Individual",  # individuals paid for services
	"M-World Logistics",  # office moving service
]

# No Thai withholding: services bought from abroad, goods, food, utilities.
EXEMPT = [
	# foreign services
	"Anthropic", "Apollo", "Artboard Studio", "Asana", "AWS", "DigitalOcean", "Envato",
	"Figma", "Google", "Hostinger", "Meta Platforms, Inc.", "NameCheap", "OpenAI, LLC", "TikTok",
	# goods and equipment
	"Apple", "Banana IT", "Belkin", "Boonthaworn", "Copperwired", "HomePro", "Ikea",
	"Index Living Mall", "LG", "Makro", "Miniso", "Mr. DIY", "Office Mates", "Samsung", "Signo",
	"Studio7", "Tuya Door Lock",
	# food and drink
	"Bankara Ramen", "BBQ Plaza", "Bonchon", "Foodland", "Nak-La Mookrata", "Starbucks", "TeeNoi Suki",
	# utilities and telecoms — different rules may apply; an accountant should confirm
	"AIS", "Metropolitan Electricity Authority", "Metropolitan Waterworks Authority",
]


def _ensure_fields():
	"""Frappe runs patches before it syncs fixtures, so on the first migrate the
	two fields from fixtures/custom_field.json don't exist yet when this patch
	runs. Create them here (same definition as the fixture, so the later
	fixture sync is a no-op). Without this the patch would find no column,
	return, be marked done, and never seed anything."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Supplier": [
				{
					"fieldname": "custom_withhold_3pct",
					"label": "Withhold 3% (Thai service)",
					"fieldtype": "Check",
					"insert_after": "supplier_group",
					"default": "0",
					"module": "Kiluth Finance",
				},
				{
					"fieldname": "custom_withholding_reviewed",
					"label": "Withholding reviewed",
					"fieldtype": "Check",
					"insert_after": "custom_withhold_3pct",
					"default": "0",
					"module": "Kiluth Finance",
				},
			]
		},
		update=False,
	)


def execute():
	_ensure_fields()
	for name in WITHHOLD + EXEMPT:
		if not frappe.db.exists("Supplier", name):
			continue
		frappe.db.set_value(
			"Supplier",
			name,
			{"custom_withhold_3pct": 1 if name in WITHHOLD else 0, "custom_withholding_reviewed": 1},
			update_modified=False,
		)
	frappe.db.commit()
