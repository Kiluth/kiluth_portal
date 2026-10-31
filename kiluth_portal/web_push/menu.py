"""Put "Phone notifications" in the v16 desk user menu.

v16's desk has no `#toolbar-user` dropdown; the sidebar header menu is built
from Navbar Settings > Settings Dropdown. An Action item there runs
`kiluth_enable_push()` (defined in public/js/web_push.bundle.js).
Runs after every migrate; adds the row once, never duplicates it.
"""

import frappe

LABEL = "Phone notifications"
ACTION = "kiluth_enable_push()"


def ensure_menu_item():
	settings = frappe.get_single("Navbar Settings")
	if any(row.action == ACTION for row in settings.settings_dropdown):
		return
	settings.append(
		"settings_dropdown",
		{"item_label": LABEL, "item_type": "Action", "action": ACTION, "icon": "bell", "is_standard": 0},
	)
	settings.save(ignore_permissions=True)
