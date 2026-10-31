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
# `web_push.bundle.js` adds "Phone notifications" to the user menu (web_push/).
app_include_js = ["navbar.bundle.js", "web_push.bundle.js"]


# Form Behavior (versioned client-side)
# -------------------------------------
# Prefer doctype_js over DB-stored Client Scripts for stable, load-bearing form
# behavior. Loose/experimental tweaks can still live as Client Script fixtures.
doctype_js = {
	"Resource": "public/js/resource.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	"Equipment Loan Agreement": "public/js/equipment_loan_agreement.js",
	"Material Request": "public/js/material_request.js",
	"User": "public/js/user.js",
}


# Scheduled Tasks
# ---------------
# Daily: re-run Resource status calc so expiry notifications fire on time even
# if nobody saves a Resource manually that day. The same logic runs on every
# Resource.before_save for single-record edits.
#
# Cron — `0 9 5 * *`: 09:00 on the 5th of each month (server time).
# Builds + emails Kiluth's monthly financial PDF report covering the prior
# full month + YTD. Recipients are hard-coded in the module. Picked the 5th
# (not the 1st) to give finance a few days for late entries to land.
#
# Hourly — catch-up: if the primary cron was missed (server down, deploy
# in flight, etc.), the hourly tick re-attempts. The function is idempotent:
# self-skips when the report for the current period has already been sent.
# So the worst case is a delayed email, never a duplicate or missed month.
# Notification messages call {{ kiluth_email(...) }} for the designed email.
jinja = {"methods": ["kiluth_portal.utils.jinja.kiluth_email"]}

scheduler_events = {
	"daily": [
		"kiluth_portal.utils.scheduler.recalc_resource_status",
		"kiluth_portal.utils.yearly_tasks.yearly_tasks_catchup",
	],
	"cron": {
		"0 9 5 * *": [
			"kiluth_portal.utils.financial_report.send_monthly_report",
		],
		# Learning reports for last month, after the 5th's financial report.
		"0 9 6 * *": [
			"kiluth_portal.kiluth_hr.learning_report.send_monthly",
		],
		# Days off this week, Mondays 08:00 (replaces the HRMS holiday reminder).
		"0 8 * * 1": [
			"kiluth_portal.kiluth_hr.holiday_reminder.send_weekly",
		],
		# Monthly Close step 1: create "Close the books for <last month>".
		"0 8 1 * *": [
			"kiluth_portal.utils.close_task.create_close_task",
		],
		# Thai withholding: last month's service payments with no 3% recorded.
		# The 3rd leaves four days before the ภ.ง.ด.3 / ภ.ง.ด.53 deadline.
		"0 8 3 * *": [
			"kiluth_portal.utils.tax_checks.withholding_check",
		],
		# Year end: ภ.ง.ด.1ก (due end Feb) and ภ.ง.ด.50 + statements (due end May).
		"0 8 5 1 *": [
			"kiluth_portal.utils.yearly_tasks.year_end_tasks",
		],
		# Half year: ภ.ง.ด.51 (due 31 Aug).
		"0 8 5 7 *": [
			"kiluth_portal.utils.yearly_tasks.half_year_task",
		],
	},
	"weekly": [
		# Income against the ฿1.8m VAT line. Silent until 75% of it.
		"kiluth_portal.utils.tax_checks.vat_threshold_watch",
	],
	"hourly": [
		"kiluth_portal.utils.financial_report.send_monthly_report_catchup",
		"kiluth_portal.kiluth_hr.learning_report.send_monthly_catchup",
		# Certificates still Pending signature after an hour: check them again.
		"kiluth_portal.kiluth_hr.certify.sweep",
		"kiluth_portal.utils.close_task.create_close_task_catchup",
		"kiluth_portal.utils.tax_checks.withholding_check_catchup",
		# Website leads nobody touched for one working day go to the Executive role too.
		"kiluth_portal.utils.lead_routing.escalate_unanswered_leads",
		# Kiluth Tasks notifications: retry Failed outbox rows (Dead at 5 tries).
		"kiluth_portal.task_notify.jobs.retry_failed",
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
    # Monthly Close: build and email the Close Report PDF when a
    # "Close the books for <Month YYYY>" task is completed.
    # Implements docs.kiluth.com/finance/monthly-close.
    "Task": {
        "on_update": "kiluth_portal.utils.close_report.on_task_update",
    },
    # Gate User creation to the kiluth.com domain — needed because Website
    # Settings has signup enabled (so Google SSO auto-provisions Kiluth staff
    # without HR having to pre-create each User record). The hook bounces any
    # email not ending in @kiluth.com.
    "User": {
        "before_insert": "kiluth_portal.utils.auth.restrict_signup_to_kiluth_domain",
    },
    # Kiluth's check on a passed certification test (kiluth_hr/certify.py).
    # Implements docs.kiluth.com/hr/certification. The record File is often
    # attached just after the Document is saved, so both events enqueue.
    "Document": {
        "on_update": "kiluth_portal.kiluth_hr.certify.on_document_update",
    },
    "File": {
        "after_insert": "kiluth_portal.kiluth_hr.certify.on_file_insert",
    },
    # Refuse a new customer whose name matches one we have (utils/customer.py).
    "Customer": {
        "before_insert": "kiluth_portal.utils.customer.block_duplicate",
    },
    # Kiluth Tasks notifications. Hooks only queue a
    # job; who is told lives in task_notify/recipients.py, delivery in
    # task_notify/channels.py.
    "ToDo": {
        "on_update": "kiluth_portal.task_notify.handlers.on_todo_change",
    },
    "Comment": {
        "after_insert": "kiluth_portal.task_notify.handlers.on_comment_insert",
    },
}


# Serves /kiluth-push-sw.js and /kiluth-manifest.webmanifest from the site root.
page_renderer = ["kiluth_portal.web_push.renderer.WebPushAssets"]


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
KILUTH_MODULES = ["Kiluth HR", "Kiluth Hosting", "Kiluth Sales", "Kiluth Legal"]

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
    "Sales",  # certified salespeople; website leads are routed among them (utils/lead_routing.py)
    "Delivery",
    "Finance",
    "HR",
    "Executive",
    "Observer",
    "Document User",
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
    "kiluth_portal.utils.print_defaults.apply_default_print_formats",
    "kiluth_portal.web_push.menu.ensure_menu_item",
]

# A completed Task keeps its assignee as holder; ERPNext would clear it.
# See kiluth_portal/overrides/task.py.
override_doctype_class = {
	"Task": "kiluth_portal.overrides.task.KiluthTask",
}
