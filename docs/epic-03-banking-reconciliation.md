# Epic 3 — Banking and Reconciliation

## Purpose
Add basic banking and bank reconciliation support so LedgerOS can manage cash movement and reconcile accounting with bank activity.

## In Scope
- Bank account ledger objects
- Bank transaction recording
- Payment receipts and vendor payments tied to bank accounts
- Bank statement import or statement entry capture
- Bank reconciliation workflow
- Reconciliation status tracking
- Cash basis support for banking transactions
- Dockerized runtime for banking and reconciliation workflows in local development, testing, and deployment

## Why this epic exists
Reliable cash accounting is required for SMB accounting and is a core part of the MVP scope. Reconciliation closes the gap between accounting records and real bank activity.

## Deliverables
- Bank account model and chart-of-accounts integration
- Bank deposit/payment transaction posting
- Reconciliation object and workflow definitions
- Imported bank statement line ingestion or manual bank statement entry support
- Matching and clearing logic for reconciled bank lines
- UI support for reconciling a bank account
- Cash-basis statement support in reporting layer

## Implementation Notes
- Implementation must use Python/Django models and Django ORM for banking and reconciliation data.
- The banking and reconciliation components must run containerized in Docker with environment-driven configuration.
- Data model should include:
  - `bank_accounts`: id, entity_id, name, account_number, bank_name, ledger_account_id
  - `bank_transactions`: id, entity_id, bank_account_id, transaction_date, amount, transaction_type, source_type, source_id, memo
  - `bank_statement_lines`: id, entity_id, bank_account_id, statement_date, amount, description, statement_reference
  - `bank_reconciliations`: id, entity_id, bank_account_id, start_date, end_date, status, statement_ending_balance, cleared_balance
  - `bank_reconciliation_matches`: reconciliation_id, statement_line_id, bank_transaction_id, matched_amount
- Bank transaction posting should always flow through a cash/bank GL account.
- Payment receipts and vendor payments should create both AR/AP application entries and bank cash entries.
- Reconciliation workflow should support:
  - importing or manually entering bank statement lines,
  - matching statement lines to ledger transactions,
  - marking matched lines as cleared,
  - calculating reconciliation status and unreconciled amounts.
- Prevent double-clearing of the same bank transaction or statement line.
- Cash-basis reporting should include bank cash movement and cleared bank balances as required for the period basis.

## Example Success Scenarios
- Record a customer payment of $800 into a bank account and verify the GL entry:
  - Debit: Bank Cash $800
  - Credit: Accounts Receivable $800
- Import a bank statement line for $800 and match it to the bank transaction.
- Create a reconciliation for the period, match lines, and verify the reconciliation closes with no unmatched balance.
- Attempt to match the same bank statement line twice and receive a validation error.

## Acceptance Criteria
- Bank account balances post correctly to the GL
- A reconciliation can be created, and statement lines matched to ledger transactions
- Reconciled transactions are marked and cannot be double-cleared
- Reconciliation preserves an audit trail of adjustments
- Cash-basis reports can reflect bank account movement appropriately
- Banking and reconciliation flows can be run and verified in Docker containers

## Testing Instructions
- Unit tests for:
  - bank account and transaction posting rules
  - statement line import validation
  - reconciliation matching and duplicate protection
  - cash-basis inclusion of bank movement
- Integration tests for:
  - recording a bank payment and verifying GL cash balance updates
  - importing statement lines and matching to posted transactions
  - finalizing a reconciliation and checking status and balances
- Regression tests to ensure bank transaction matches are immutable once reconciled.

## Dependencies
- Epic 1: Foundational Accounting Core
- Epic 2: AR/AP

## Approval
- Status: **Pending**
- Approval required before any code is built against this epic.
