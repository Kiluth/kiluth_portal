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
