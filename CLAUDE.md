## Project-Specific Guidelines: Accounting Core System

This system handles financial records. Treat accounting behavior as high-risk.

Before coding:
- State domain assumptions explicitly.
- Identify whether the change affects ledger entries, reports, balances, payments, invoices, reconciliations, taxes, 
owner statements, tenant ledgers, or audit trails.
- If accounting treatment is ambiguous, stop and ask.

Simplicity:
- Prefer explicit domain functions over generalized abstractions.
- Do not create a generic accounting engine unless multiple concrete use cases already require it.
- Avoid speculative configurability.

Surgical changes:
- Every changed line must trace to the requested behavior.
- Do not refactor unrelated ledger, payment, or reporting code.
- Do not rename accounts, enums, or transaction types without migration and test coverage.

Goal-driven execution:
- For every accounting change, define success using examples:
  - expected journal entries
  - expected account balances
  - expected owner statement line items
  - expected tenant ledger entries
  - expected report totals
- Write or update tests before implementation when behavior changes.
