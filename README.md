# Kiluth Portal

Kiluth's custom Frappe app for [portal.kiluth.com](https://portal.kiluth.com) — runs alongside ERPNext + HRMS to provide:

- **Custom doctypes** — Resource (domain/hosting/MA tracking), Equipment Loan Agreement + Equipment Return, New Employee Application, Resource Type
- **Tiled portal landing page** at `/welcome` with category filtering + search
- **Concern-area roles** — Commercial, Delivery, Finance, HR, Executive, Observer (separate from native ERPNext roles)
- **Procurement catalog** — 8 timeless anchor Items (Laptop, Monitor, Peripheral, etc.) wired into Material Request flow
- **Notifications** — Kiluth-flavored alerts for resources, leaves, expenses, equipment loans
- **Branding hooks** — auto-applied on `bench migrate` so the portal logo/favicon survive deploys

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/Kiluth/kiluth_portal --branch main
bench install-app kiluth_portal
bench migrate
```

For full local-dev setup with Docker Compose, see [Kiluth/frappe_docker](https://github.com/Kiluth/frappe_docker).

## Google SSO setup (one-time per environment)

Frappe's "Sign in with Google" is wired through a `Social Login Key` DB record,
not a fixture (the OAuth secret is environment-specific and shouldn't live in
git). After a fresh deploy, run the following on the backend container:

```python
# bench --site portal.kiluth.com console

import frappe

doc = frappe.get_doc({
    "doctype": "Social Login Key",
    "provider_name": "Google",
    "social_login_provider": "Google",
    "client_id": "<client-id-from-gcp>",
    "client_secret": "<client-secret-from-gcp>",
    "base_url": "https://accounts.google.com",
    "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "access_token_url": "https://accounts.google.com/o/oauth2/token",
    "redirect_url": "/api/method/frappe.integrations.oauth2_logins.login_via_google",
    "api_endpoint": "https://www.googleapis.com/oauth2/v2/userinfo",
    "auth_url_data": '{"response_type": "code", "scope": "openid profile email"}',
    "user_id_property": "email",
    "icon": "fa fa-google",
    "enable_social_login": 1,
})
doc.insert(ignore_permissions=True)
frappe.db.commit()
```

Notes:

- `api_endpoint` must be the **v2** userinfo URL — Frappe's `update_oauth_user`
  reads `data["id"]`, which v3 replaced with `sub`.
- The GCP OAuth client must have
  `https://<host>/api/method/frappe.integrations.oauth2_logins.login_via_google`
  in its **Authorized redirect URIs**.
- After insertion run `bench --site <site> clear-cache` so the login page
  picks up the new provider on the next render.

## Contributing

This app uses `pre-commit` for code formatting and linting. [Install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/kiluth_portal
pre-commit install
```

Pre-commit runs:

- `ruff` — Python lint + format
- `eslint` — JS lint
- `prettier` — JS/JSON/Markdown format
- `pyupgrade` — modernize Python syntax

## License

MIT
