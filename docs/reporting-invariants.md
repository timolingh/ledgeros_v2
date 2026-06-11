# Reporting Invariants

This document defines required accounting/reporting behavior for LedgerOS.

Reporting code must be judged by accounting semantics, not by whether report endpoints return data.

## 1. Reports Must Use Signed Accounting Meaning

Reports must not blindly sum journal line amounts.

Journal lines must be interpreted according to account type and debit/credit side.

For profit and loss:

| Account type | Debit line | Credit line |
|---|---:|---:|
| Revenue | decreases revenue | increases revenue |
| Expense | increases expense | decreases expense |

For balance sheet:

| Account type | Debit line | Credit line |
|---|---:|---:|
| Asset | increases balance | decreases balance |
| Liability | decreases balance | increases balance |
| Equity | decreases balance | increases balance |

Required tests:

- credit revenue increases revenue,
- debit revenue decreases revenue,
- debit expense increases expense,
- credit expense decreases expense,
- customer credit memo reduces revenue,
- vendor credit memo reduces expense.

## 2. Period Reports Must Be Period-Specific Unless Named Otherwise

A report for a date range must include only activity within that date range.

Do not use cumulative-as-of balances for fields named period activity.

Examples:

- Period posted debits must include only entries dated within the period.
- Period posted credits must include only entries dated within the period.
- Period journal entry count must include only entries dated within the period.

If a report is cumulative, name it explicitly as cumulative or as-of.

Bad:

- `posted_debits` using all activity through period end date.

Good:

- `period_posted_debits` using period activity only.
- `ending_trial_balance` using cumulative balances as of period end.

Required tests:

- January activity must not appear in May period activity.
- Prior-period balances may appear only in explicitly named ending/as-of fields.

## 3. Balance Sheet Is As-Of, Profit and Loss Is Period-Based

Balance sheet reports are cumulative as of a date.

Profit and loss reports are activity-based for a start/end date.

Required behavior:

- Balance sheet requires `as_of_date`.
- Balance sheet must not accept start/end period filters unless explicitly designed.
- Profit and loss requires `start_date` and `end_date`.
- Profit and loss must not include activity outside that range.

Required tests:

- pre-period revenue is excluded from P&L,
- in-period revenue is included in P&L,
- post-period revenue is excluded from P&L,
- prior asset balances are included in balance sheet as of date.

## 4. Accrual and Cash Basis Must Be Explicit

Accrual-basis P&L recognizes income and expenses from posted revenue and expense journal lines within the reporting period.

Cash-basis P&L recognizes income and expenses according to the documented cash-recognition event.

For LedgerOS MVP, if cash-basis reporting recognizes income/expense when payments are applied, document that explicitly.

If cash-basis reporting recognizes income/expense only when bank transactions clear, document that explicitly.

Do not mix both interpretations silently.

Required tests:

- unpaid invoice appears in accrual P&L,
- unpaid invoice does not appear in cash P&L,
- paid invoice appears in cash P&L according to the chosen recognition point,
- unpaid bill appears in accrual P&L,
- unpaid bill does not appear in cash P&L,
- paid bill appears in cash P&L according to the chosen recognition point.

## 5. Current Earnings Must Be Derived, Not Posted

Balance sheet current earnings must be derived from revenue and expense activity.

Do not require a closing entry for MVP balance sheet to balance.

Required tests:

- balance sheet balances when revenue exceeds expenses,
- current earnings equals revenue minus expenses,
- assets equal liabilities plus equity plus current earnings.

## 6. Drill-Down Must Reconcile to Report Totals

Every report total exposed in the API should have a drill-down path or a documented reason why drill-down is deferred.

Drill-down rows must sum to the displayed report amount.

Required tests:

- revenue drill-down rows sum to revenue total,
- expense drill-down rows sum to expense total,
- cash-basis drill-down rows sum to cash-basis totals,
- contra lines appear with negative sign where appropriate.

## 7. Tax Reporting Must Distinguish Mapping From Calculation

Tax code/account mapping is not the same as tax calculation.

If tax calculation is not implemented, explicitly mark these as deferred:

- invoice-line tax code selection,
- automatic tax amount calculation,
- posting tax liability from invoices,
- sales tax collected by jurisdiction,
- use tax accrual,
- tax return/export workflow.

Do not mark “sales tax collected on AR invoices” as implemented unless AR invoice posting actually creates and reports tax liability lines.

Required tests if implemented:

- taxable invoice posts revenue and tax liability separately,
- tax summary reports collected tax by jurisdiction,
- non-taxable invoice does not affect tax liability,
- customer credit reduces tax liability if applicable.

## 8. Reports Must Be Immutable Views Over Posted Accounting Data

Reports must derive from posted entries and approved operational records only.

Draft journal entries must not affect reports.

Unposted invoices, bills, or payments must not affect reports unless the report explicitly says it includes draft/pro forma data.

Required tests:

- draft journal entries excluded from balance sheet,
- draft journal entries excluded from accrual P&L,
- draft invoices excluded from accrual P&L,
- draft bills excluded from accrual P&L.

## 9. Every Report Must Define Its Basis, Scope, and Sign Rules

Each reporting service must document:

- whether it is as-of or period-based,
- whether it is accrual, cash, or both,
- which source records it uses,
- how signs are calculated,
- what statuses are included,
- what is explicitly excluded.

This documentation can live in the service docstring and the epic README.

## 10. Manual Acceptance Checks Are Required

Epic reporting implementations must include manual checks that create known accounting activity and verify report results.

At minimum, checks must include:

- normal revenue,
- contra revenue,
- normal expense,
- contra expense,
- prior-period activity exclusion,
- draft exclusion,
- balance sheet current earnings,
- cash vs accrual difference,
- drill-down totals matching report totals.