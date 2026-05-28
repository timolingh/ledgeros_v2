# LedgerOS Epic 1 Structured Copy-Paste Implementation

This folder is a standalone minimal Django project plus a modular `apps/accounting` app for Epic 1: Foundational Accounting Core.

It uses the stronger structure discussed after the first implementation: project config is separated from domain apps, accounting internals are split into models/services/selectors/API, and later epics can be added as sibling apps without polluting the ledger core.

## Scope implemented

- PostgreSQL-first Django project
- Split settings: `config/settings/base.py`, `local.py`, `test.py`, `production.py`
- Hidden default entity for MVP
- Chart of accounts model and YAML import
- Accounting periods with `open`, `closed`, and `locked` states
- Draft journal entries
- Posting service with balanced debit/credit enforcement
- Locked/closed period validation
- Reversal service that creates a posted reversing entry and marks the original as reversed
- Ledger-affecting balance selectors that include posted entries and reversed originals; draft entries are excluded
- Draft entries may be updated before posting; posted and reversed entries are not destructively editable
- Corrections happen through reversal plus a new entry, not by editing posted accounting facts
- Immutable audit logs for successful material accounting actions only
- Thin DRF endpoints for core Epic 1 resources, using Django/DRF default authentication
- Docker Compose for local app + PostgreSQL runtime
- Unit/integration tests for core accounting behavior
- `docs/accounting-core-invariants.md` as the normative ledger rules document
- `scripts/check.sh` as the repeatable Docker validation command

## Structure

```text
manage.py
pyproject.toml
Dockerfile
docker-compose.yml
.env.example
config/
  settings/
    base.py
    local.py
    test.py
    production.py
  urls.py
  asgi.py
  wsgi.py
  sample_chart_of_accounts.yml
apps/
  accounting/
    models/
      accounts.py
      periods.py
      journals.py
      audit.py
    services/
      entities.py
      audit.py
      periods.py
      posting.py
      reversal.py
      chart_import.py
    selectors/
      balances.py
    api/
      serializers.py
      views.py
      urls.py
    management/commands/import_coa.py
    migrations/0001_initial.py
    tests/
docs/
  accounting-core-invariants.md
scripts/
  check.sh
```

## Explicit domain assumptions

- MVP uses one hidden default entity. Public/API callers do not choose an entity.
- Draft entries do not affect account balances.
- Only posted entries and reversed originals affect ledger balances; a reversing posted entry offsets the original.
- Posted entries are not destructively editable. They must be reversed.
- Reversal entries cannot be reversed; corrections are always made by reversing the original posted entry only.
- Closed/locked behavior follows the Epic 1 period lifecycle: open accepts postings; closed and locked reject postings.
- This implementation logs successful accounting state changes only. Blocked/failed attempts raise validation errors but do not create audit rows.
- Future-scoped checklist items that depend on later accounting features are intentionally excluded from the Epic 1 acceptance list rather than modeled as failing tests.
- Epic 5 external accounting event ingestion, API client YAML auth, idempotency keys, and invoice/payment event APIs are intentionally not implemented here.
- Epic 6 full role model, UI permission matrix, browser UI, CSV import/export, and deployment polish are intentionally not implemented here.

## Copy into your repo

From your local `epic_01` checkout, copy the contents of this folder into the repo root.

## Local run

```bash
cp .env.example .env
docker compose up --build -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
docker compose up web
```

Open the app at `http://localhost:8000/admin/` or use the API at `http://localhost:8000/api/v1/`.

## Run tests

Use the project validation script:

```bash
./scripts/check.sh
```

The script runs the same Docker commands explicitly:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

## Core service examples

Create an accounting period:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import create_accounting_period

period = create_accounting_period(
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    name="FY2026",
)

print(period.id)
print(period.name)
print(period.start_date)
print(period.end_date)
print(period.status)
PY
```

Create and post a balanced entry:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import JournalLineInput, create_and_post_journal_entry

entry = create_and_post_journal_entry(
    entry_date=date(2026, 5, 1),
    description="Record cash sale",
    lines=[
        JournalLineInput(account_code="1000", side="debit", amount="1000.00"),
        JournalLineInput(account_code="4000", side="credit", amount="1000.00"),
    ],
)
PY
```

View account balances in Python:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.selectors import trial_balance

for row in trial_balance():
    print(row["account_code"], row["name"], row["balance"])
PY
```

Or fetch balances through the Epic 1 API:

```bash
curl -u <username>:<password> http://localhost:8000/api/v1/accounts/ | jq
```

The account payload includes `posted_balance` for each account. That field is computed through the balance selector layer.

Reverse the last posted entry:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.models import JournalEntry
from apps.accounting.services import reverse_journal_entry

entry = JournalEntry.objects.filter(status="posted").latest("id")

reversal = reverse_journal_entry(
    entry=entry,
    reversal_date=date(2026, 5, 2),
)

print("Original:", entry.id, entry.status)
print("Reversal:", reversal.id, reversal.status)
PY
```

## API surface included

These are thin Epic 1 core endpoints, not the Epic 5 external event ingestion API.

- `GET /api/v1/entities/`
- `GET/POST/PATCH /api/v1/accounts/`; generic `PUT` and `DELETE` are disabled.
- `GET/POST/PATCH /api/v1/periods/`; `status` cannot be patched directly.
- `POST /api/v1/periods/{id}/change_status/` for period status transitions.
- `GET/POST /api/v1/journal-entries/`; create always produces a draft.
- `PATCH /api/v1/journal-entries/{id}/` for draft-only edits; generic `PUT` and `DELETE` are disabled.
- `POST /api/v1/journal-entries/{id}/post/` for posting.
- `POST /api/v1/journal-entries/{id}/reverse/` for reversal.
- `GET /api/v1/audit-logs/`; audit logs are read-only.

DRF uses Django session/basic authentication and requires authenticated users by default. Full MVP role enforcement belongs to Epic 6.

## Ledger invariants

Read `docs/accounting-core-invariants.md` before changing ledger behavior. It defines the service-layer, posting, reversal, period, balance, and audit rules that future epics must preserve.

## Manual acceptance checks

1. Import `config/sample_chart_of_accounts.yml`.
2. Create an accounting period covering today.
3. Create a draft journal entry debiting Cash and crediting Revenue for the same amount.
4. Confirm the draft does not change balances.
5. Post it and verify account balances changed.
6. Attempt an unbalanced journal entry and verify posting is rejected.
7. Close the period and verify posting is rejected.
8. Lock the period and verify new postings inside it are rejected.
9. Reverse the posted entry and verify the original remains visible and balances net back to zero.
10. Confirm audit logs exist for COA import, period change, journal creation, posting, and reversal.

## Out-of-scope acceptance items

These behaviors are either already enforced through the service layer or are deferred to later epics, so they are not part of the active Epic 1 manual checklist:

- Any parent-account / non-posting-account constraints that require later account hierarchy support.
