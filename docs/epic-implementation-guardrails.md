# Epic Implementation Guardrails

This document defines required implementation discipline for LedgerOS epics.

The goal is to prevent partial, ambiguous, or superficially complete implementations. Every epic must be traceable from PRD/epic requirements to code, tests, and manual acceptance checks.

Before implementing or reviewing an epic, read:

- `CLAUDE.md`
- `docs/accounting-core-invariants.md`
- `docs/reporting-invariants.md`
- the relevant epic specification
- the PRD sections that touch the epic

## 1. Requirement Traceability Is Required

Before writing code for an epic, create a short requirement traceability checklist from the PRD and the current epic document.

Every requirement must be classified as exactly one of:

- **Implemented in this epic**
- **Explicitly deferred to a later epic**
- **Out of scope**
- **Ambiguous / requires clarification**

Do not begin implementation until every acceptance criterion and every major PRD requirement touching the epic has one of those classifications.

If a requirement is ambiguous and affects behavior, data model, accounting treatment, API shape, permissions, or acceptance tests, stop and ask for clarification.

## 2. Requirement Traceability Matrix

Every epic implementation must include a traceability matrix in the epic README or implementation notes.

Use this format:

| Requirement | Source | Status | Code location | Test / manual check |
|---|---|---|---|---|
| Example: bank transaction creates posted GL entry | Epic 3 | Implemented | `apps/accounting/services/banking.py` | `apps/accounting/tests/test_banking_services.py` |
| Example: reconciliation rejects duplicate match | Epic 3 | Implemented | `apps/accounting/models/banking.py` | `apps/accounting/tests/test_banking_services.py` |
| Example: banking API endpoints | PRD / Epic 3 | Deferred | N/A | Documented deferred |

Status values must be one of:

- **Implemented**
- **Partially implemented**
- **Deferred**
- **Out of scope**
- **Blocked / needs clarification**

Do not mark an item **Implemented** unless the implementation has both code and a test or manual acceptance check.

For partially implemented items, state exactly:

- what works,
- what does not work,
- what is deferred,
- and what proves the current behavior.

## 3. No Silent Partial Implementation

Do not describe an epic as complete if any acceptance criterion is only partially implemented.

If a feature is deferred, document the deferral clearly in the epic README or implementation notes.

A deferred feature should include:

- the reason it is deferred,
- the likely future epic where it belongs,
- whether any placeholder or hook was added,
- and whether the current code is safe without it.

Bad:

> Banking implemented.

Better:

> Banking service layer implemented. Banking API endpoints and UI reconciliation workflow are deferred.

## 4. PRD and Epic Conflict Rule

If the PRD and the current epic document conflict, do not silently choose one.

Default rule:

1. The current epic controls implementation scope.
2. The PRD controls long-term product direction.
3. Conflicts must be documented.
4. Behavior-changing conflicts require clarification.

If a decision is made to implement the epic differently from older PRD wording, add a note to the epic README or implementation notes.

Example:

> Epic 1 implements `open / closed / locked` accounting periods. Earlier PRD language referencing `soft_closed` is deferred and not part of the Epic 1 implementation.

## 5. Required Pre-Implementation Checklist

Before writing code for an epic, produce a checklist with these sections.

### 5.1 Domain Objects Required

Identify:

- new models,
- changed existing models,
- removed or deprecated fields,
- migrations required,
- database constraints required,
- admin/API exposure, if any.

### 5.2 State-Changing Workflows

Identify every workflow that changes accounting state.

For each workflow, specify:

- service function name,
- allowed inputs,
- validation rules,
- journal entry impact,
- audit log impact,
- failure behavior,
- tests required.

Examples:

- `post_journal_entry(...)`
- `reverse_journal_entry(...)`
- `apply_payment_to_invoice(...)`
- `record_bank_transaction(...)`
- `complete_bank_reconciliation(...)`

### 5.3 Cross-Epic Integration Points

Identify whether the epic touches prior or future domains:

- accounting core,
- AR/AP,
- banking,
- reconciliation,
- reporting,
- API integrations,
- permissions,
- UI,
- deployment.

If an integration is required by the epic, implement and test it.

If an integration is deferred, document the deferral.

### 5.4 Acceptance Criteria Mapping

Each acceptance criterion must map to at least one of:

- model/migration,
- service function,
- selector/report,
- API/admin path,
- automated test,
- manual acceptance command.

Manual acceptance checks must be runnable through Docker.

### 5.5 Non-Goals

List features intentionally not implemented.

For each non-goal, say whether it is:

- future epic work,
- explicitly out of scope,
- blocked pending product decision.

## 6. Accounting Integration Rule

When an epic introduces or modifies an accounting workflow, verify both sides of the workflow.

### 6.1 Operational Record

The workflow must create or update the operational record.

Examples:

- invoice,
- bill,
- payment,
- payment application,
- bank account,
- bank transaction,
- bank statement line,
- bank reconciliation,
- reconciliation match.

### 6.2 General Ledger Impact

The workflow must create or reference the correct posted journal entry.

The journal entry must:

- preserve double-entry accounting,
- use correct debit and credit signs,
- post only to an open accounting period,
- use active posting accounts,
- preserve auditability,
- be testable through balance selectors.

If a workflow affects cash, AR, AP, revenue, expense, clearing accounts, or bank balances, tests must prove both the operational record and the GL/account balance effect.

Examples:

- Customer invoice must debit AR and credit revenue.
- Customer payment must credit AR and debit the configured receipt or clearing account.
- Vendor bill must debit expense or asset and credit AP.
- Vendor payment must debit AP and credit the configured payment or clearing account.
- Bank deposit must debit the bank ledger account and credit the offset account.
- Bank withdrawal must debit the offset account and credit the bank ledger account.
- Bank reconciliation must validate matched bank transactions and statement lines.

## 7. Reconciliation Integrity Rule

Any reconciliation feature must test both happy paths and negative cases.

Required negative tests:

- duplicate matching is rejected,
- amount mismatch is rejected,
- sign mismatch is rejected,
- cross-bank-account matching is rejected,
- cross-entity matching is rejected,
- out-of-period statement lines are rejected,
- out-of-period bank transactions are rejected,
- reconciliation cannot complete with unmatched statement lines,
- reconciliation cannot complete when the relevant cleared/book balance does not match the statement balance.

Do not consider reconciliation complete if only the happy path is tested.

## 8. Service-Layer Mutation Rule

State-changing accounting behavior must go through service-layer functions.

Views, serializers, admin actions, management commands, tests, and future integrations must not directly mutate critical accounting state.

Do not directly assign or save fields such as:

- `JournalEntry.status`
- `JournalEntry.posted_at`
- `JournalEntry.reversed_at`
- `JournalEntry.reversal_of`
- `AccountingPeriod.status`
- audit log fields
- reconciliation completion status
- bank transaction posting links

Bad:

```python
entry.status = "posted"
entry.save()
```

Good:

```python
post_journal_entry(entry=entry)
```

Bad:

```python
reconciliation.status = "completed"
reconciliation.save()
```

Good:

```python
complete_bank_reconciliation(reconciliation=reconciliation)
```

## 9. Interface Thinness Rule

Interfaces should be thin.

Admin, API, and management commands should:

- parse input,
- call services,
- return results,
- avoid duplicating business rules.

Business rules belong in:

- `apps/accounting/services/`
- `apps/accounting/selectors/`
- model validation only when it protects core invariants.

Admin and API must not implement their own separate accounting logic.

## 10. Reporting Traceability Rule

For reporting epics, every report must define:

- source records,
- included statuses,
- excluded statuses,
- date semantics,
- basis semantics,
- sign semantics,
- drill-down behavior,
- tests for contra activity.

A report endpoint returning JSON is not sufficient. The JSON must match accounting meaning.

Required reporting test matrix:

| Scenario | Balance sheet | Accrual P&L | Cash P&L | Drill-down |
|---|---:|---:|---:|---:|
| Normal revenue | current earnings affected | included | depends on payment | reconciles |
| Contra revenue | current earnings reduced | negative revenue | depends on payment | reconciles |
| Normal expense | current earnings affected | included | depends on payment | reconciles |
| Contra expense | current earnings increased | negative expense | depends on payment | reconciles |
| Prior-period activity | included only if as-of | excluded | excluded | excluded |
| Draft activity | excluded | excluded | excluded | excluded |

## 11. Manual Acceptance Checks

Every epic README must include Docker-ready manual acceptance checks.

Manual checks should be copy-paste runnable from the repo root.

Use this style:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
# Python acceptance check here.
PY
```

For database verification, SQL checks are allowed and encouraged:

```bash
docker compose exec db psql -U ledgeros -d ledgeros -c "
select *
from some_table
order by id desc
limit 10;
"
```

Manual acceptance checks should verify observable state, not just that commands run.

Examples of observable state:

- journal entry posted,
- account balance changed,
- bank account balance changed,
- reconciliation status became completed,
- audit log was written,
- invalid operation was rejected.

## 12. Automated Test Expectations

Every implemented requirement should have automated test coverage unless there is a documented reason manual verification is sufficient.

Tests should cover:

- the happy path,
- important negative cases,
- accounting balance effects,
- audit log effects,
- service-layer enforcement,
- admin/API mutation restrictions where applicable.

For accounting workflows, prefer behavior tests over implementation-detail tests.

Good test names describe accounting behavior:

```text
test_posting_unbalanced_journal_entry_is_rejected
test_reversal_offsets_original_entry_balance
test_closed_period_rejects_posting
test_bank_reconciliation_rejects_amount_mismatch
```

Avoid tests that only prove objects can be created without validating accounting meaning.

## 13. Validation Before Handoff

Before claiming an epic is complete, run the project validation sequence.

Required:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

If the epic includes custom management commands, run the relevant commands manually.

If the epic includes migrations, run:

```bash
docker compose run --rm web python manage.py migrate
```

If the epic includes accounting seed data, run:

```bash
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
```

If any command cannot be run in the current environment, say so explicitly and provide the exact command the user should run.

## 14. No Unreviewed Scope Expansion

Do not implement later-epic functionality just because it is easy to scaffold.

Before adding any of the following, confirm it is part of the current epic:

- external API ingestion,
- HMAC API clients,
- idempotency-key handling,
- browser UI,
- role matrix,
- permissions framework,
- reporting dashboards,
- cash-basis statements,
- bank feed import automation,
- deployment infrastructure.

If future hooks are necessary, keep them minimal, inert, documented, and tested.

## 15. Done Means Traceable

An epic is not done until the following are true:

- requirements are classified,
- implemented requirements map to code,
- implemented requirements map to tests or manual checks,
- deferred items are documented,
- acceptance checks are runnable,
- validation commands pass,
- docs and code use the same vocabulary.

If code and docs disagree, the epic is not done.
