# LedgerOS Backend Accounting System

LedgerOS is a Docker-first Django/PostgreSQL backend for double-entry accounting, accounts receivable, accounts payable, banking/reconciliation, reporting, and external API ingestion.

This README is the quick-start entry point. For full operating instructions, see `docs/user-manual.md`.

## What is implemented

LedgerOS currently includes:

- Foundational double-entry ledger with entities, accounts, accounting periods, journal entries, posting, reversal, balances, and audit logs.
- Accounts receivable and accounts payable workflows for customers, vendors, invoices, bills, payments, and credits.
- Banking and reconciliation models/services for bank accounts, bank transactions, statement lines, reconciliation matches, and completed reconciliations.
- Reporting and tax-code support for saved report views, balance sheet, profit and loss, period summary, tax summary, and drill-downs.
- External API ingestion for invoices, bills, payments, credits, and refunds using configured API clients, HMAC authentication, scopes, event types, idempotency, and response replay.
- Docker Compose local runtime with Django and PostgreSQL.

Development and verification are Docker-first:

- Run the app in `docker compose`.
- Run Django checks and tests in the `web` container.
- Do not rely on host-side Python for normal development or validation.

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
```

For local API client testing, also configure the API client config path and secret environment variable in `.env` or your shell:

```bash
LEDGEROS_API_CLIENTS_CONFIG=/app/api_clients.yml
LEDGEROS_API_CLIENT_FULL_SECRET=replace-this-with-a-local-secret
```

Do not commit real secrets.

### 2. Build containers

```bash
docker compose build
```

### 3. Start PostgreSQL

```bash
docker compose up -d db
```

### 4. Run migrations

```bash
docker compose run --rm web python manage.py migrate
```

### 5. Import the sample chart of accounts

```bash
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
```

### 6. Create an admin user

```bash
docker compose run --rm web python manage.py createsuperuser
```

### 7. Run the application

```bash
docker compose up web
```

Open:

- Django Admin: `http://localhost:8000/admin/`
- API root: `http://localhost:8000/api/v1/`

## Smoke test

Run the validation script:

```bash
./scripts/check.sh
```

Or run the underlying checks directly:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

## Documentation map

Primary docs:

- `docs/user-manual.md` — setup, operating workflows, bookkeeper UI requirements, and API client setup.
- `docs/technical-spec.md` — architecture, domain model, service/API design, and major decisions.
- `docs/ai-agent-guidance.md` — rules for AI agents making future code changes.
- `docs/feature-roadmap.md` — committed next work and future product candidates.

Normative implementation docs:

- `docs/accounting-core-invariants.md`
- `docs/reporting-invariants.md`
- `docs/api-auth-idempotency.md`
- `docs/api-client-config-schema.md`
- `docs/epic-implementation-guardrails.md`

Historical epic implementation notes remain in the repo:

- `README_EPIC_01_IMPLEMENTATION.md`
- `README_EPIC_02_IMPLEMENTATION.md`
- `README_EPIC_03_IMPLEMENTATION.md`
- `README_EPIC_04_IMPLEMENTATION.md`
- `README_EPIC_05_IMPLEMENTATION.md`

## Production note

This repository is currently Docker-first and backend-first. Django Admin is suitable for setup, inspection, and internal testing. A dedicated bookkeeper-facing UI and production deployment hardening are roadmap items.
