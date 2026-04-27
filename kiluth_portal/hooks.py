app_name = "kiluth_portal"
app_title = "Kiluth Portal"
app_publisher = "Kiluth LTD."
app_description = "Kiluth's custom Frappe app for portal.kiluth.com — custom doctypes, hooks, fixtures, and the tiled portal landing page"
app_email = "technology@kiluth.com"
app_license = "mit"


# Desk-wide assets
# ----------------
# Loaded on every /app page. Frappe v16 resolves this through its bundler, so
# the entry must be a `.bundle.js` file living under `public/js/`.
# `navbar.bundle.js` re-routes the Kiluth logo and inserts a dedicated "Portal"
# link so users can always jump back to the portal home from the desk.
app_include_js = "navbar.bundle.js"


# Form Behavior (versioned client-side)
# -------------------------------------
# Prefer doctype_js over DB-stored Client Scripts for stable, load-bearing form
# behavior. Loose/experimental tweaks can still live as Client Script fixtures.
doctype_js = {
	"Resource": "public/js/resource.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	"Equipment Loan Agreement": "public/js/equipment_loan_agreement.js",
	"Material Request": "public/js/material_request.js",
}


# Scheduled Tasks
# ---------------
# Daily: re-run Resource status calc so expiry notifications fire on time even
# if nobody saves a Resource manually that day. The same logic runs on every
# Resource.before_save for single-record edits.
scheduler_events = {
	"daily": [
		"kiluth_portal.utils.scheduler.recalc_resource_status",
	],
}


# Document Events
# ---------------
# Kept deliberately small and explicit. Each target lives in utils/ as a
# versioned Python function (not a Server Script in the DB), because these
# hooks are load-bearing for inventory accuracy and payroll correctness.
doc_events = {
    "Equipment Loan Agreement": {
        "on_submit": "kiluth_portal.utils.asset_movement.sync_on_loan",
    },
    "Equipment Return": {
        "on_submit": "kiluth_portal.utils.asset_movement.sync_on_return",
    },
    "Expense Claim": {
        "before_insert": "kiluth_portal.utils.employee.autofill_employee",
    },
    "Leave Application": {
        "before_insert": "kiluth_portal.utils.employee.autofill_employee",
    },
    "Timesheet": {
        "before_insert": "kiluth_portal.utils.employee.autofill_employee",
    },
    # Gate User creation to the kiluth.com domain — needed because Website
    # Settings has signup enabled (so Google SSO auto-provisions Kiluth staff
    # without HR having to pre-create each User record). The hook bounces any
    # email not ending in @kiluth.com.
    "User": {
        "before_insert": "kiluth_portal.utils.auth.restrict_signup_to_kiluth_domain",
    },
}


# Post-login landing page
# -----------------------
# Override Frappe's default redirect (desk users go to /app) so every login
# lands on the Kiluth portal page (Web Page named "portal", route "welcome").
# Frappe's `get_default_path` calls this hook before falling back to /app.
get_website_user_home_page = "kiluth_portal.utils.auth.get_user_home_page"


# OAuth callback override
# -----------------------
# Wrap Frappe's Google login callback so a stale `redirect_to=/desk` baked
# into the OAuth state (from /login?redirect-to=/desk) doesn't trump the
# home-page hook above. See utils/auth.py:login_via_google for the rationale.
override_whitelisted_methods = {
    "frappe.integrations.oauth2_logins.login_via_google": "kiluth_portal.utils.auth.login_via_google",
}


# Fixtures
# --------
# Records exported by `bench export-fixtures --app kiluth_portal` and
# re-imported by `bench migrate`. Keeps UI-editable artifacts (Client Scripts,
# Notifications, Print Formats, etc.) reproducible across environments.
#
# Filters scope the export to Kiluth-authored records only, so we don't
# accidentally serialize ERPNext / HRMS stock artifacts.
KILUTH_MODULES = ["Kiluth HR", "Kiluth Hosting", "Kiluth Sales"]

KILUTH_WEB_PAGES = ["portal", "holidays", "convert-document"]
KILUTH_HOLIDAY_LISTS = ["Kiluth Thailand Holiday 2025", "Kiluth Thailand Holiday 2026"]

# Kiluth Catalog — the timeless 8-item procurement catalog backing Material
# Request flow. Item Groups form a tree under "Kiluth Catalog"; Items sit in
# the leaf groups. Filters below only export records inside this tree, so
# stock ERPNext sample items / groups never land in the fixture.
KILUTH_CATALOG_ITEM_GROUPS = [
    "Kiluth Catalog",
    "Hardware",
    "Laptop",
    "Monitor",
    "Peripheral",
    "Audio",
    "Networking",
    "Furniture",
    "Software",
    "Other",
]
KILUTH_CATALOG_ITEMS = [
    "LAPTOP", "MONITOR", "PERIPHERAL", "AUDIO",
    "NETWORKING", "FURNITURE", "SOFTWARE", "OTHER",
]

# Kiluth concern-area roles. Filtering Custom DocPerm exports by role name
# keeps the fixture scoped to Kiluth's own access model and skips the stock
# ERPNext/HRMS rules that already ship in their modules.
KILUTH_CUSTOM_ROLES = [
    "Commercial",
    "Delivery",
    "Finance",
    "HR",
    "Executive",
    "Observer",
]

# Specific standard doctypes where we grant extra roles outside the concern
# model (e.g. Issue, Material Request for Employee access). Kept narrow so
# we don't accidentally export stock rules on unrelated doctypes.
KILUTH_CUSTOM_DOCPERM_PARENTS = ["Issue", "Material Request", "Supplier"]

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    {
        "doctype": "Property Setter",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    {
        "doctype": "Client Script",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    {
        "doctype": "Server Script",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    {
        "doctype": "Notification",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    {
        "doctype": "Print Format",
        "filters": [["module", "in", KILUTH_MODULES]],
    },
    # Portal landing + companion pages (holidays, convert-document) and the
    # branded welcome page powering /welcome.
    {
        "doctype": "Web Page",
        "filters": [["name", "in", KILUTH_WEB_PAGES]],
    },
    # Thai public holiday calendars (load-bearing for Leave Application +
    # Salary Slip working-day calculations).
    {
        "doctype": "Holiday List",
        "filters": [["name", "in", KILUTH_HOLIDAY_LISTS]],
    },
    # Kiluth concern-area Role records.
    {
        "doctype": "Role",
        "filters": [["name", "in", KILUTH_CUSTOM_ROLES]],
    },
    # All DocPerm rules backing the concern-area roles (Commercial, Delivery,
    # Finance, HR, Executive, Observer), plus the narrow set of extra role
    # grants on specific standard doctypes (Issue, Material Request, Supplier).
    {
        "doctype": "Custom DocPerm",
        "filters": [
            [
                "role",
                "in",
                KILUTH_CUSTOM_ROLES
                + ["Employee", "HR Manager", "Purchase Manager", "System Manager"],
            ]
        ],
    },
    # Kiluth Catalog: Item Group tree + 8 anchor Items. Timeless procurement
    # catalog — specifics (model, specs) go in the MR description, not the Item.
    {
        "doctype": "Item Group",
        "filters": [["name", "in", KILUTH_CATALOG_ITEM_GROUPS]],
    },
    {
        "doctype": "Item",
        "filters": [["item_code", "in", KILUTH_CATALOG_ITEMS]],
    },
    # Seed records on custom doctypes (e.g. Resource Type: Server, Domain, MA).
    # Doctypes are added to this list once they exist.
    # {"doctype": "Resource Type"},
]


# After-migrate hooks
# -------------------
# Run on every `bench migrate` to set defaults that can't be expressed as
# fixtures (e.g. singleton Website Settings fields). Each callback is
# idempotent — safe to run repeatedly.
after_migrate = [
    "kiluth_portal.utils.website.apply_website_settings",
]
