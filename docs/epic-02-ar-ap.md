# Epic 2 — Accounts Receivable and Accounts Payable

## Purpose
Implement core AR/AP workflows so LedgerOS can manage customer invoices, vendor bills, payments, credits, and refunds as accounting records.

## In Scope
- Customer records
- Vendor records
- Invoice accounting records
- Bill accounting records
- Accounts receivable balances
- Accounts payable balances
- Payments, credits, and refunds
- Internally generated invoice numbers for UI-created invoices
- Externally supplied invoice numbers for API-created invoices
- AR/AP journal entry generation and application

## Why this epic exists
MVP success requires the system to process receivables and payables as accounting transactions, while preserving the boundary that LedgerOS is not a business workflow engine.

## Deliverables
- Customer and vendor ledger object models
- Invoice and bill creation workflows in the accounting module
- Payment application to invoices and bills
- Credit memo/credit application support
- Refund handling for AR/AP where applicable
- Journal entry templates for invoice issuance, bill issuance, payment, credit, refund
- Validation rules for missing customer/vendor or invalid period

## Implementation Notes
- Data model should include:
  - `customers`: id, entity_id, name, customer_code, default_ar_account_id, status
  - `vendors`: id, entity_id, name, vendor_code, default_ap_account_id, status
  - `invoices`: id, entity_id, customer_id, invoice_number, external_invoice_number, date, due_date, total_amount, status
  - `bills`: id, entity_id, vendor_id, bill_number, external_bill_number, date, due_date, total_amount, status
  - `invoice_lines` / `bill_lines`: line_description, amount, account_id
  - `payments`: id, entity_id, source_type, source_id, amount, payment_date, account_id
  - `payment_applications`: payment_id, invoice_id/bill_id, applied_amount
  - `refunds`: id, entity_id, original_payment_id, amount, refund_date
- Invoice issuance should generate a journal entry that debits AR and credits revenue or appropriate income account.
- Bill issuance should generate a journal entry that debits expense or asset account and credits AP.
- Customer payment application should generate a journal entry that debits cash/bank and credits AR.
- Vendor payment should generate a journal entry that debits AP and credits cash/bank.
- Credits should reduce AR/AP balances and may generate offsetting journal entries.
- Refunds should reverse payment cash flow and adjust AR/AP or cash accounts accordingly.
- Numbering:
  - UI-created invoices/bills receive internal invoice_number/bill_number.
  - API-created invoices/bills may carry external_invoice_number from the sender.
- Keep workflow focused on accounting records; do not implement CRM/customer onboarding or vendor purchase workflows.

## Example Success Scenarios
- Create a customer invoice for $500 on an open period:
  - Debit: Accounts Receivable $500
  - Credit: Sales Revenue $500
- Apply a customer payment of $500 to the invoice:
  - Debit: Cash $500
  - Credit: Accounts Receivable $500
- Create a vendor bill for $300 and mark it payable:
  - Debit: Expense $300
  - Credit: Accounts Payable $300
- Pay the vendor bill from bank account:
  - Debit: Accounts Payable $300
  - Credit: Bank Cash $300

## Acceptance Criteria
- UI or API can create invoices and bills with correct AR/AP posting
- Payments applied to invoices/bills update outstanding balances correctly
- System accepts external invoice numbers for API-submitted documents
- System generates internal numbering for UI-created invoices
- Customer/vendor ledger balances reconcile with GL balances
- AR/AP work without exposing non-accounting business workflow behavior

## Testing Instructions
- Unit tests for:
  - invoice and bill journal generation rules
  - payment application to invoices and bills
  - credit and refund posting behavior
  - external invoice number handling
- Integration tests for:
  - invoice -> payment -> AR balance reconciliation
  - bill -> vendor payment -> AP balance reconciliation
  - invalid customer/vendor or invalid period rejection
  - internal vs external numbering paths
- Regression tests for AR/AP aging and outstanding balance calculations if implemented.

## Dependencies
- Epic 1: Foundational Accounting Core

## Approval
- Status: **Pending**
- Approval required before any code is built against this epic.
