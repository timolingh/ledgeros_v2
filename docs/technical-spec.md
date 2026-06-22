# LedgerOS Technical Specification

This document explains the current LedgerOS backend architecture and captures the major design decisions behind it. It is both an implementation guide and a decision record.

## 1. System overview

LedgerOS is a Django/PostgreSQL accounting backend. It is organized around double-entry accounting invariants, service-layer workflows, read-side selectors, and thin API/admin interfaces.

Implemented domains:

- Accounting core: entities, accounts, periods, journal entries, journal lines, posting, reversal, balances, audit logs.
- AR/AP: customers, vendors, invoices, bills, payments, payment applications, credits.
- Banking and reconciliation: bank accounts, transactions, statement lines, reconciliations, matches.
- Reporting and tax: saved report views, tax codes, balance sheet, profit and loss, drill-downs, period summary, tax summary.
- External API ingestion: API client config, HMAC authentication, scopes, event types, idempotency records, response replay, customer/invoice/bill/payment/credit/refund submissions.

## 2. Project layout

```text
config/                  Django project configuration
apps/accounting/          Accounting domain app
  models/                 Domain data models
  services/               State-changing business workflows
  selectors/              Read-side queries, balances, reporting helpers
  api/                    DRF serializers, views, auth, URLs
  management/commands/    Operational commands such as chart import
  migrations/             Database migrations
  tests/                  Executable accounting invariants and API tests
docs/                     Normative specs, invariants, roadmap, guidance
scripts/                  Repeatable local validation scripts
```

The core rule is:

```text
models are nouns
services are verbs
selectors are questions
APIs/admin are interfaces, not business-rule owners
```

## 3. Runtime architecture

LedgerOS is Docker-first.

- `web`: Django application container.
- `db`: PostgreSQL database container.
- `.env`: local environment configuration.
- `api_clients.yml`: YAML API client config, with secret values referenced through environment variables.

Local validation is performed with:

```bash
./scripts/check.sh
```

## 4. Domain model overview

### Accounting core

Primary models:

- `Entity`
- `Account`
- `AccountingPeriod`
- `JournalEntry`
- `JournalLine`
- `AuditLog`

Key lifecycle:

```text
draft journal entry -> posted journal entry -> reversed original + posted reversing entry
```

Draft entries do not affect balances. Posted entries affect balances. Posted entries are corrected through reversal, not destructive edits.

Accounting periods control posting:

```text
open   -> postings allowed
closed -> postings rejected
locked -> postings rejected
```

### AR/AP

Primary models:

- `Customer`
- `Vendor`
- `Invoice`
- `InvoiceLine`
- `Bill`
- `BillLine`
- `Payment`
- `PaymentApplication`
- `CreditMemo`

Accounting impact:

- Invoice posting: debit AR, credit revenue.
- Bill posting: debit expense/asset, credit AP.
- Customer payment: debit Undeposited Funds, credit AR.
- Vendor payment: debit AP, credit Undeposited Funds.
- Customer credit: reverse/reduce customer receivable/revenue according to service logic.
- Vendor credit: reverse/reduce vendor payable/expense according to service logic.

### Banking and reconciliation

Primary models:

- `BankAccount`
- `BankTransaction`
- `BankStatementLine`
- `BankReconciliation`
- `BankReconciliationMatch`

Banking services create operational records and associated GL impact. Reconciliation validates that statement lines and bank transactions belong to the same bank account/entity and that match amounts and directions are coherent.

Bank-event ingestion through the external API is deferred.

### Reporting and tax

Primary models:

- `ReportView`
- `TaxCode`

Primary services/selectors:

- `generate_balance_sheet`
- `generate_profit_and_loss`
- `generate_report_drilldown`
- `run_report_view`
- `summarize_period`
- `tax_summary`

Reports are read-side outputs over posted accounting data. Reporting behavior must follow `docs/reporting-invariants.md`.

### API integration

Primary model:

- `ApiRequestRecord`

It stores:

- entity
- client ID
- event type
- idempotency key
- nonce
- request hash
- request payload
- response status/payload
- resulting domain object and journal entry references

This enables duplicate request detection and original response replay.

## 5. Service layer

State-changing accounting behavior belongs in services.

Important services include:

- `create_accounting_period`
- `change_period_status`
- `create_draft_journal_entry`
- `post_journal_entry`
- `create_and_post_journal_entry`
- `reverse_journal_entry`
- `post_invoice`
- `post_bill`
- `apply_payment_to_invoice`
- `apply_payment_to_bill`
- `issue_customer_credit`
- `issue_vendor_credit`
- `record_bank_transaction`
- `create_bank_statement_line`
- `match_bank_statement_line`
- `complete_bank_reconciliation`
- `submit_invoice_event`
- `submit_bill_event`
- `submit_payment_event`
- `submit_credit_event`

Services are responsible for:

- validation,
- period enforcement,
- double-entry balance,
- audit logging,
- status transitions,
- journal entry creation,
- idempotency handling for API ingestion,
- preserving accounting invariants.

## 6. Selector layer

Selectors answer questions without owning business workflows.

Examples:

- posted balances,
- trial balance,
- reporting data,
- reconciliation read-side queries.

Model methods may provide thin convenience wrappers, but canonical balance/report logic belongs in selectors/services.

## 7. API layer

The API layer uses Django REST Framework.

Core/resource endpoints are mounted under:

```text
/api/v1/
```

Implemented route families include:

```text
/entities/
/accounts/
/periods/
/journal-entries/
/reports/
/tax-codes/
/audit-logs/
/customers/
/invoices/
/bills/
/payments/
/credits/
/refunds/
```

The API should remain thin:

- validate transport-level shape,
- authenticate/authorize,
- call services,
- serialize responses,
- avoid owning accounting business rules.

Generic destructive writes are intentionally limited. Posted accounting records should be changed through explicit service-backed actions, not generic PUT/DELETE mutation.

## 8. Epic 5 external API design

Epic 5 uses a hybrid surface:

- resource-shaped HTTP endpoints,
- event-shaped business semantics.

Current write endpoints:

```text
POST /api/v1/customers/ -> customer.upsert_requested
POST /api/v1/invoices/  -> invoice.post_requested
POST /api/v1/bills/     -> bill.post_requested
POST /api/v1/payments/  -> payment.post_requested
POST /api/v1/credits/   -> credit.post_requested
POST /api/v1/refunds/   -> refund.post_requested
```

Authentication:

- HMAC is required for write requests.
- API-key-only writes are not the intended safe path.
- Client scopes and allowed event types are enforced.

Idempotency:

- Idempotency is scoped by entity, client, event type, and idempotency key.
- Duplicate matching payloads return the original stored success payload.
- Same key with different payload is rejected.
- Nonces are unique per client.

## 9. Admin layer

Django Admin is transitional. It is useful for setup, inspection, and internal testing. It is not the long-term non-technical bookkeeping UI.

Admin must not become the place where accounting invariants are bypassed. Admin actions should call services.

## 10. Audit logging

Audit logs record successful material actions and selected authentication failures.

Audit logs must not store secrets, raw authorization headers, HMAC signatures, or reusable replay material.

## 11. Testing and validation strategy

Tests must prove accounting behavior, not just object creation.

Expected coverage includes:

- balanced posting,
- draft exclusion from balances,
- period close/lock rejection,
- reversal behavior,
- AR/AP GL effects,
- payment application GL effects,
- bank transaction GL effects,
- reconciliation validation,
- report totals and drill-downs,
- API authentication,
- API idempotency,
- API scope/event authorization.

Docker validation:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

## 12. Major design decisions

### ADR-001: Docker-first local runtime

Decision: LedgerOS assumes Docker for local setup and validation.

Rationale: Docker keeps Django, PostgreSQL, migrations, tests, and API behavior consistent across developers and agents.

### ADR-002: PostgreSQL-first backend

Decision: LedgerOS targets PostgreSQL rather than SQLite-compatible minimalism.

Rationale: Accounting systems rely on transactional integrity, constraints, and realistic deployment behavior. PostgreSQL is the production-like default.

### ADR-003: Hidden default entity for MVP

Decision: MVP uses one default entity instead of exposing full multi-entity selection everywhere.

Rationale: This reduces product and permission complexity while preserving entity scoping in the data model.

Deferred: user-facing multi-entity selection, entity switching, and multi-entity permissions.

### ADR-004: Service-layer mutations

Decision: State-changing accounting workflows belong in services.

Rationale: APIs, admin screens, commands, and future UIs must share the same accounting rules.

### ADR-005: Draft/posted/reversed lifecycle

Decision: Journal entries move from draft to posted, and corrections happen through reversal.

Rationale: Posted accounting facts should remain auditable. Destructive edits undermine ledger integrity.

### ADR-006: Closed and locked periods reject postings

Decision: `closed` and `locked` both reject new postings.

Rationale: MVP period behavior should be simple and safe. Any future controlled reopen or adjustment workflow should be explicit.

### ADR-007: Successful material actions are audited

Decision: Audit logs capture successful material accounting actions; selected API authentication failures may also be logged.

Rationale: The ledger needs a record of successful state changes. Failed validation attempts should not pollute accounting history unless security-relevant.

### ADR-008: AR/AP operational records create GL impact through services

Decision: Invoices, bills, payments, and credits are operational records that produce or reference posted journal entries.

Rationale: Operational workflows and the general ledger must stay reconciled.

### ADR-009: Undeposited Funds as MVP payment clearing

Decision: Customer/vendor payments use an Undeposited Funds clearing account before bank movement.

Rationale: This separates payment application from bank deposit/withdrawal and keeps AR/AP workflows independent from reconciliation timing.

### ADR-010: Banking API ingestion is deferred

Decision: Epic 5 external API MVP excludes bank event ingestion.

Rationale: Bank feeds and reconciliation introduce different validation, matching, and duplicate-detection risks. They should be handled as focused future work.

### ADR-011: Reports use services/selectors

Decision: Reports are generated through reporting services/selectors rather than direct UI logic.

Rationale: Report sign rules, date scope, basis, and drill-down reconciliation need central enforcement.

### ADR-012: Hybrid external API shape

Decision: Epic 5 uses resource-shaped endpoints with event-shaped semantics.

Rationale: Resource endpoints are easier for client implementers while event semantics preserve auditability, idempotency, and source-system traceability.

### ADR-013: HMAC for write requests

Decision: External write requests require HMAC authentication.

Rationale: API-key-only writes are too weak for accounting mutations. HMAC provides request integrity and replay protection when paired with timestamp/nonce validation.

### ADR-014: Full original response replay for idempotency

Decision: Duplicate idempotent requests return the original stored success payload.

Rationale: Clients can safely retry without writing special duplicate-handling logic.

### ADR-015: External uniqueness scoped by entity and integration client

Decision: External invoice/bill references are treated as client-scoped.

Rationale: Different source systems may emit the same human invoice number. Client scoping avoids cross-system collisions.

### ADR-016: Minimal API client YAML schema

Decision: API client config includes only fields the implementation uses.

Rationale: Unused optional config creates false completeness and validation burden.

## 13. Deferred decisions and non-goals

Deferred or intentionally incomplete areas:

- Production bookkeeper-facing UI.
- Role-based permissions and detailed permission matrix.
- Production deployment hardening.
- Multi-entity user-facing workflows.
- Bank-feed ingestion API.
- Automated bank transaction matching.
- Sales-tax calculation and liability posting from invoices.
- Full tax return/export workflow.
- Expanded cash-basis reporting beyond implemented payment-application semantics.
- Property/tenant/owner domain workflows.
- Attachments and document storage.
- Webhooks and outbound integration events.
- OpenAPI schema generation.

## 14. Normative documents

Future work must respect:

- `docs/accounting-core-invariants.md`
- `docs/reporting-invariants.md`
- `docs/api-auth-idempotency.md`
- `docs/api-client-config-schema.md`
- `docs/epic-implementation-guardrails.md`
- `docs/ai-agent-guidance.md`
