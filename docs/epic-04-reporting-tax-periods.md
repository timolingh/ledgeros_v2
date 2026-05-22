# Epic 4 — Reporting, Periods, and Tax Support

## Purpose
Deliver MVP financial reporting, period management, and US/California tax accounting support.

## In Scope
- Standard financial reports (balance sheet, income statement)
- Cash-basis and accrual-basis reporting support
- Configurable standard reports and saved views
- Report drill-down support
- Report APIs
- Accounting period summaries and closing period controls
- US and California tax accounting support for MVP
- Dockerized runtime for reporting, tax, and period management in local development, testing, and deployment

## Why this epic exists
Users need auditable financial statements and period controls to close the books reliably, while meeting the MVP tax scope.

## Deliverables
- Report generation engine for GL-based standard reports
- Basis selector for cash vs accrual reporting
- Saved report definitions and report view persistence
- Drill-down navigation into underlying journal entries
- Report API endpoints for programmatic access
- Period reporting and audit summary views
- Tax account mapping and US/CA tax reporting support

## Implementation Notes
- Implementation must use Python/Django services for report generation and Django ORM for report data access.
- Reporting and tax services must run containerized in Docker and assume Docker-friendly deployment configuration.
- Reporting engine should derive reports from posted journal entries, not mutable UI state.
- Standard report definitions:
  - Balance Sheet: asset, liability, equity account groups as of a date.
  - Profit & Loss: income and expense account groups for a date range.
- Cash vs accrual rules:
  - Accrual report uses journal entry dates and AR/AP balances.
  - Cash report includes only cash/bank receipts and disbursements for the period.
- Saved report views should persist report type, date range, basis, filters, and display settings.
- Drill-down should expose the underlying journal entries or payments that compose each report line.
- Accounting period reports should surface period status and disallow transactions in closed periods.
- Tax support should include:
  - sales tax collected on AR invoices
  - sales/use tax liability account mapping
  - US/California tax-specific liability or expense account structure for MVP
  - tax reporting lines in financial statements or separate tax summary if needed.
- Period management:
  - `open`, `close`, `lock` states with transitions documented.
  - closed periods prevent posting; locked periods prevent reopening.

## Example Success Scenarios
- Generate a balance sheet at 2026-05-31 and verify total assets equals total liabilities plus equity.
- Generate a profit & loss report for April 2026 on accrual basis and verify revenue and expense totals come from posted journal entries.
- Generate the same date range on cash basis and verify only bank cash receipts/disbursements appear.
- Save a report view and retrieve it later through the UI/API.
- Record a sales tax liability and verify it appears on the tax support summary.
- Close a period and confirm posting is rejected for dates within that period.

## Acceptance Criteria
- Users can generate balance sheet and profit & loss reports
- Reports can be generated on cash and accrual bases
- Saved report views persist and can be retrieved via UI/API
- Drill-down opens underlying transaction details
- Period locking prevents posting to closed periods and is reflected in reports
- US and California tax support is available in the accounting schema and reporting outputs
- Reporting, period, and tax workflows can be exercised in Dockerized environments

## Testing Instructions
- Unit tests for:
  - report line aggregation by account type
  - cash vs accrual basis selection rules
  - saved report view persistence and retrieval
  - period status enforcement in report generation
  - tax account mapping and report line inclusion
- Integration tests for:
  - generating balance sheet and P&L from sample journal entries
  - comparing cash and accrual outputs for the same period
  - retrieving a saved report view and matching expected configuration
  - closing a period and verifying transactions are excluded from new postings
- Regression tests around US/CA tax reporting rules if specific tax mappings are implemented.

## Dependencies
- Epic 1: Foundational Accounting Core
- Epic 2: AR/AP
- Epic 3: Banking and Reconciliation

## Approval
- Status: **Pending**
- Approval required before any code is built against this epic.
