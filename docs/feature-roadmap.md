# LedgerOS Feature Roadmap

This roadmap separates committed next work from future candidates. It is not a promise that every candidate will be built. Each future epic must still go through requirements, decisions, tests, and acceptance checks.

## 1. Roadmap principles

1. Preserve accounting correctness before adding convenience.
2. Prefer service-backed workflows over raw data editing.
3. Keep the bookkeeper experience simple and safe.
4. Keep API ingestion secure, idempotent, and auditable.
5. Separate implemented behavior from deferred behavior.
6. Avoid broad platform abstractions until there is a concrete workflow that needs them.

## 2. Committed next work

These are the most natural next work packages after the current backend state.

### 2.1 Epic 6: UI, permissions, and deployment hardening

Epic 6 is the natural next implementation package.

Recommended scope:

- Bookkeeper-facing web UI.
- Role-based permissions.
- Production deployment hardening.
- Operational setup screens.
- API client observability/status screens.
- CSV import/export for practical operations.

Rationale: The backend now has accounting workflows, reports, banking/reconciliation, and API ingestion. The next bottleneck is safe human operation and production readiness.

### 2.2 Bookkeeper-facing web UI

Goal: allow a non-technical bookkeeper to enter and review accounting data without using Django Admin.

Initial screens:

- Dashboard
- Customers
- Invoices
- Customer payments
- Vendors
- Bills
- Vendor payments
- Bank accounts
- Bank transactions
- Bank reconciliation
- Reports
- Audit/history

Required design constraints:

- No raw status editing.
- No destructive editing of posted records.
- Explicit actions for post, reverse, apply payment, issue credit, match, and complete reconciliation.
- Human-readable validation errors.
- Clear status indicators.

### 2.3 Role-based permissions

Goal: separate technical administrators, bookkeepers, reviewers, and read-only users.

Candidate roles:

- System administrator
- Accounting administrator
- Bookkeeper
- Reviewer/approver
- Reporting-only user
- API client observer

Required decisions:

- Which roles can post?
- Which roles can reverse?
- Which roles can close/lock periods?
- Which roles can configure API clients?
- Which roles can view audit logs?

### 2.4 Production deployment hardening

Goal: make deployment safer outside local Docker.

Candidate work:

- Production environment checklist.
- Strong secret management.
- HTTPS/proxy assumptions.
- Database backup/restore procedure.
- Logging and monitoring guidance.
- Health checks.
- Static files configuration.
- Error tracking hooks.

### 2.5 CSV import/export

Goal: support practical migration and operations workflows.

Candidate imports:

- Customers
- Vendors
- Chart of accounts
- Opening balances
- Invoices
- Bills
- Payments
- Bank statement lines

Candidate exports:

- Trial balance
- General ledger detail
- Invoices
- Bills
- Payments
- Audit logs
- Reports

## 3. Near-term productization

These items make the current backend easier to operate but may not all belong in Epic 6.

### 3.1 Reconciliation UI

The backend has reconciliation services. A useful UI should support:

- Statement-line import/review.
- Candidate bank transaction matching.
- Manual match adjustment.
- Duplicate-match prevention.
- Completion checklist.
- Reconciliation report.

### 3.2 Saved report UX

Improve report operation:

- Saved report templates.
- Common report date presets.
- Drill-down from totals.
- Export to CSV/PDF.
- Report comparison periods.

### 3.3 API client observability

External API ingestion should become easier to monitor:

- API request history.
- Recent failures.
- Duplicate/idempotent replay count.
- Client enabled/disabled status.
- Scope and event-type display.
- Secret rotation checklist.

Secrets should remain outside the database/UI.

### 3.4 Generic sync/event boundary

If a downstream product needs LedgerOS to persist non-core workflow events, prefer one generic external-event or sync-event API over a family of domain-specific endpoints.

Rationale: LedgerOS stays a slim accounting backend while downstream applications retain ownership of their business-domain semantics, such as property-specific security deposit logic.

### 3.5 Operational runbook

Add a production runbook:

- Setup checklist.
- Period close checklist.
- Backup/restore steps.
- Troubleshooting API authentication.
- Troubleshooting failed postings.
- Incident response for duplicate external submissions.

## 4. Future candidates

These are useful candidates but should not be treated as implemented or committed until planned.

### 4.1 Bank-feed ingestion

Potential scope:

- External bank transaction import API.
- Bank statement file import.
- Duplicate detection.
- Automated matching candidates.
- Match confidence scoring.
- Review queue.

Reason deferred: banking/reconciliation has different integrity risks than AR/AP ingestion and deserves a focused epic.

### 4.2 Automated transaction matching

Potential scope:

- Date/amount/reference matching.
- Customer/vendor name matching.
- Suggested match queue.
- Rules engine for recurring transactions.
- Human approval before final match.

### 4.3 Sales-tax automation

Potential scope:

- Tax code selection on invoice lines.
- Automatic tax calculation.
- Tax liability posting.
- Jurisdiction-level tax summary.
- Credit/refund tax adjustment.
- Tax return/export workflow.

Reason deferred: current tax support is mapping/reporting-oriented, not full tax calculation and liability automation.

### 4.4 Expanded cash-basis reporting

Potential scope:

- Explicit cash-basis recognition policy.
- Cash-basis P&L drill-down.
- Payment allocation details.
- Partial payment handling.
- Cash-basis tax reporting support.

### 4.5 Multi-entity UI

Potential scope:

- User-facing entity selection.
- Entity-specific permissions.
- Consolidated reports.
- Intercompany workflows.

Reason deferred: MVP uses a hidden default entity.

### 4.6 Property/tenant/owner workflows

Potential scope:

- Properties
- Units
- Tenants
- Leases
- Rent charges
- Owner statements
- Security deposits
- Management fees

This should be its own product epic because it introduces domain workflows beyond the accounting backend.

### 4.7 Approval workflows

Potential scope:

- Bill approval.
- Payment approval.
- Journal entry approval.
- Period close approval.
- Audit trail for approvals.

### 4.8 Attachments and document storage

Potential scope:

- Attach PDFs/images to invoices, bills, payments, bank transactions, and reconciliations.
- Store metadata in LedgerOS.
- Use external object storage for files.
- Add virus scanning and access controls.

### 4.9 Recurring invoices and bills

Potential scope:

- Recurring templates.
- Scheduled generation.
- Preview before posting.
- Auto-post policy decisions.

### 4.10 OpenAPI schema generation

Potential scope:

- Public API schema.
- Generated client examples.
- Contract tests.
- Versioned API docs.

### 4.11 Webhooks and outbound events

Potential scope:

- Emit events when invoices/bills/payments are posted.
- Delivery retry.
- Signing outbound events.
- Webhook logs.

## 5. Explicit non-goals for now

Do not implement these unless specifically requested:

- Cryptocurrency accounting.
- Payroll.
- Inventory accounting.
- Full tax filing.
- Payment processing/card charging.
- Bank-feed aggregation integrations.
- Multi-tenant SaaS billing platform features.
- Complex consolidation accounting.

## 6. Suggested epic sequence

### Epic 6: UI, permissions, deployment hardening

Primary goal: make the backend operable by real users.

### Epic 7: CSV import/export and migration tooling

Primary goal: make onboarding and data movement practical.

### Epic 8: Bank-feed ingestion and reconciliation UI

Primary goal: turn banking/reconciliation into a practical daily workflow.

### Epic 9: Tax automation

Primary goal: move from tax mapping/reporting support to actual tax calculation and liability posting.

### Epic 10: Property/tenant/owner workflows

Primary goal: build domain-specific workflows on top of the accounting engine.

## 7. Roadmap hygiene rules

For every future epic:

- Create a traceability matrix.
- Identify implemented, deferred, out-of-scope, and ambiguous requirements.
- Ask clarification questions before coding ambiguous accounting behavior.
- Add automated tests for accounting invariants.
- Add Docker-ready manual acceptance checks.
- Update user manual, technical spec, AI guidance, and roadmap as needed.
