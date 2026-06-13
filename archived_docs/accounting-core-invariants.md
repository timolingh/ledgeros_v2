# Accounting Core Invariants

This document defines the Epic 1 ledger rules that future changes must preserve. If code, tests, or docs disagree with this file, stop and resolve the inconsistency before adding features.

## Scope boundary

Epic 1 owns the general ledger core: entities, chart of accounts, accounting periods, journal entries, journal lines, balance selectors, chart-of-accounts import, and audit records for successful state changes.

Epic 1 does not implement AR/AP subledgers, bank reconciliation, external event ingestion, API-client authentication, idempotency keys, role matrices, browser UI workflows, or reporting/tax modules. Later epics may call the accounting services, but they must not bypass them.

## Entity model

The MVP exposes a single hidden default entity. Every account, accounting period, journal entry, journal line, and audit log belongs to that entity path so future multi-entity support does not require replacing the ledger schema.

Application callers should use `get_default_entity()` instead of letting public/API callers choose an entity during Epic 1.

## Account rules

Each account has a type and normal balance:

- Asset and expense accounts normally carry debit balances.
- Liability, equity, and revenue accounts normally carry credit balances.

Only active accounts can be resolved for new journal lines. Chart-of-accounts import must reject account definitions whose normal balance does not match the account type.

## Accounting period rules

Epic 1 period statuses are exactly:

- `open`
- `closed`
- `locked`

Open periods accept postings. Closed and locked periods reject postings.

Allowed period transitions are:

- `open -> closed`
- `open -> locked`
- `closed -> open`
- `closed -> locked`

Locked periods are terminal in Epic 1. A locked period cannot be reopened or changed.

## Journal entry lifecycle

Epic 1 journal entry statuses are exactly:

- `draft`
- `posted`
- `reversed`

Allowed lifecycle transitions are:

- `draft -> posted`
- `posted -> reversed`

A draft entry may be edited through service-backed write paths. A posted or reversed entry must not be destructively edited. Corrections happen through reversal plus a new entry, not by changing posted accounting facts.

Draft entries must be balanced before they are saved by the provided service path. This makes a draft a validated, unposted journal entry rather than an incomplete work-in-progress object.

## Posting rules

Posting a journal entry must go through `post_journal_entry()` or another service that delegates to it. Interfaces such as Django admin, DRF views, management commands, or future integrations must not manually set `status = "posted"`.

A journal entry is postable only when:

- it is currently `draft`;
- it has at least two lines;
- every line has a positive amount;
- every line side is debit or credit;
- all line accounts are active and belong to the same entity;
- total debits equal total credits;
- total debit and credit amounts are non-zero;
- the entry date resolves to an accounting period;
- the resolved accounting period is `open`.

Posting is atomic. Either the journal entry status, posting timestamp, period assignment, and audit log all persist together, or none of them persist.

## Reversal rules

Reversal must go through `reverse_journal_entry()` or another service that delegates to it.

A normal posted journal entry may be reversed once. Reversing creates a new posted journal entry with debit and credit sides flipped, links that entry to the original through `reversal_of`, and marks the original as `reversed`.

A reversal entry cannot itself be reversed. To restore an original economic effect, create a new normal journal entry with an explicit description instead of building reversal chains.

Reversed original entries remain part of the historical ledger. The posted reversal entry offsets them.

## Balance rules

Balance calculation belongs in selectors, especially `apps.accounting.selectors.balances`. Models may keep compatibility wrappers, but selector functions are the canonical read path for balance/reporting math.

Draft entries do not affect balances.

Ledger-affecting statuses are:

- `posted`
- `reversed`

This means a reversed original remains included in historical activity, while its posted reversal offsets it.

Debit-normal account balance is:

```text
debits - credits
```

Credit-normal account balance is:

```text
credits - debits
```

## Audit rules

Audit logs record successful material accounting state changes only. Failed validations raise errors but do not create audit records.

Audit logs are immutable through normal application surfaces. They are not the source of truth for balances; posted journal lines are.

## Service-layer rule

Anything that changes accounting state must go through the accounting service layer.

Allowed examples:

- `create_accounting_period()`
- `change_period_status()`
- `create_draft_journal_entry()`
- `update_draft_journal_entry()`
- `post_journal_entry()`
- `create_and_post_journal_entry()`
- `reverse_journal_entry()`
- `import_chart_of_accounts()`

Disallowed examples outside services/migrations/tests:

```python
entry.status = "posted"
entry.save()

period.status = "locked"
period.save()

AuditLog.objects.create(...)
```

Admin, API, command, and future epic code should be thin interfaces over the same service functions.
