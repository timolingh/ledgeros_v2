# Epic 1 — Foundational Accounting Core

## Purpose
Build the core accounting engine and data model that makes LedgerOS an authoritative financial system of record.

## In Scope
- Chart of accounts
- General ledger
- Journal entry posting
- Accounting period lifecycle
- Period locking
- Balanced-book enforcement
- Single hidden default entity for MVP
- PostgreSQL schema and migrations
- Immutable audit trail baseline for posted entries
- YAML-based chart of accounts configuration
- Dockerized application runtime for local development, testing, and deployment

## Why this epic exists
This epic delivers the fundamental accounting controls required by the MVP. Without a reliable ledger, no other accounting workflow or report can be trusted.

## Deliverables
- Core ledger schema and domain model
- Account class/enums for account types and natural balances
- Journal entry creation, validation, and posting
- Debit/credit balancing rules enforced in code
- Accounting period open/close and lock behavior
- Single-entity assumption enforced in data model and UI
- Chart-of-accounts import from YAML
- Initial audit log capture for ledger changes
- User-facing documentation that explains how to manually test core accounting functionality

## Implementation Notes
- Implementation must use Python/Django models and Django ORM for the core ledger schema.
- The accounting core must run containerized in Docker, with runtime configuration suitable for Docker Compose or equivalent orchestration.
- Data model should include at minimum:
  - `accounts`: account_code, name, type, normal_balance, entity_id, is_active
  - `journal_entries`: id, entity_id, date, description, period_id, status, source, created_by
  - `journal_lines`: journal_entry_id, account_id, amount, side (debit/credit), description
  - `accounting_periods`: id, entity_id, start_date, end_date, status (open/closed/locked)
  - `audit_logs`: action, record_type, record_id, user_id, source, timestamp, metadata
  - `entities`: hidden default entity created at setup for MVP
- Business rules:
  - A posted journal entry must balance: total debits == total credits.
  - Unposted/draft entries may be allowed only if the MVP design supports draft workflows; otherwise require immediate posting.
  - Postings must belong to the default entity and use its default chart of accounts.
  - Closed or locked periods reject new journal entries and modifications.
- Chart-of-accounts YAML format should be explicit and versionable.
  Example:
  ```yaml
  accounts:
    - code: 1000
      name: Cash
      type: asset
      normal_balance: debit
    - code: 2000
      name: Accounts Payable
      type: liability
      normal_balance: credit
  ```
- Audit trail should record create/update/delete attempts on journal entries and any period state changes.

## Example Success Scenarios
- Create a `Cash` account and a `Revenue` account, then post a journal entry:
  - Debit: Cash $1,000
  - Credit: Revenue $1,000
  Result: ledger balances reflect $1,000 asset increase and $1,000 equity/income increase.
- Attempt to post a journal entry dated inside a locked period and receive a rejection error.
- Load a YAML COA file and verify account records are created or updated.

## Acceptance Criteria
- System can create and post balanced journal entries
- All posted entries belong to the hidden default entity
- Accounting periods can be opened, closed, and locked
- Closed periods reject new postings or modifications
- A YAML chart of accounts can be loaded into the system
- Audit trail records every posted entry creation and modification attempt
- The accounting core can be started and exercised in Docker containers

## Testing Instructions
- Unit tests for:
  - account type classification and natural balance logic
  - journal entry balance validation
  - period status validation for posting
  - YAML COA parsing and account creation
- Integration tests for:
  - posting a complete journal entry and verifying GL balances
  - preventing postings into closed/locked periods
  - saving audit log entries for journal creation and period changes
- Regression tests for hidden default entity enforcement.

## Dependencies
- PostgreSQL production database
- No external business-layer integration required for MVP

## Approval
- Status: Approved
- Approval required before any code is built against this epic.
