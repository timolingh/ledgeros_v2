# LedgerOS Epic 2 AR/AP Implementation

This document describes the Accounts Receivable and Accounts Payable implementation for LedgerOS, building on the foundational accounting core from Epic 1.

## Scope Implemented

- Customer records with AR account defaults
- Vendor records with AP account defaults
- Invoice accounting records with line items and AR/AP posting
- Bill accounting records with line items and AR/AP posting
- Customer payment application with GL posting
- Vendor payment application with GL posting
- Customer credit memo issuance with GL posting
- Vendor credit memo issuance with GL posting
- Invoice and bill status lifecycle tracking
- Outstanding balance calculation for invoices and bills
- Internal invoice/bill numbering (external numbers supported for API sources)
- Unit and integration tests for all AR/AP workflows
- Service-layer architecture preserving accounting invariants
- Dockerized runtime for local development, testing, and deployment

## Structure

```text
apps/accounting/
  models/
    ar_ap.py                    # Customer, Vendor, Invoice, Bill, Payment, etc.
  services/
    ar_ap.py                    # Invoice/bill posting, payment application, credits
  tests/
    test_ar_ap_models.py        # Model validation and constraint tests
    test_ar_ap_services.py      # Service-layer integration tests
  migrations/
    0004_bill_customer_...      # AR/AP model schema
```

## Explicit Domain Assumptions

- MVP uses one hidden default entity; customers and vendors belong to that entity.
- Each customer has an optional default AR account; if omitted, posting is rejected until configured.
- Each vendor has an optional default AP account; if omitted, posting is rejected until configured.
- Invoice and bill lines may override the default account (e.g., different revenue/expense accounts per line).
- Invoices and bills must be in DRAFT status to be posted; status transitions are unidirectional.
- Only draft invoices/bills may be edited destructively; posted and voided items must be reversed or credited, not edited.
- Draft invoices/bills do not affect balances; only posted invoices/bills create GL impact.
- Invoice posting creates: Debit AR, Credit revenue account(s).
- Bill posting creates: Debit expense account(s), Credit AP.
- Customer payment application creates: Debit cash/bank, Credit AR.
- Vendor payment application creates: Debit AP, Credit cash/bank.
- Payment application creates a PaymentApplication record and updates invoice/bill status (PARTIALLY_PAID or PAID).
- Credits reduce outstanding balances through PaymentApplication records and create reversing GL entries.
- Customer credits reduce AR; vendor credits reduce AP.
- AR and AP balances are calculated from posted invoices/bills minus applied payments and credits.
- Outstanding balance is calculated from total_amount minus sum of PaymentApplication.applied_amount.
- All accounting state changes go through the service layer and create audit logs.
- External invoice numbers are supported and must be unique per entity; internal invoice numbers are also unique per entity.

## Local Run

Starting from a running Docker environment with Epic 1 core:

```bash
# Migrations are applied automatically when container starts
docker compose run --rm web python manage.py migrate

# Import the sample chart of accounts (required for AR/AP accounts to exist)
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml

# Create an accounting period (required for posting invoices/bills/payments)
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import create_accounting_period

period = create_accounting_period(
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    name="FY2026",
)

print(f"Created period: {period.name}")
PY

# Create a customer
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Customer, Account, Entity

entity = Entity.get_default()
ar_account = Account.objects.get(entity=entity, account_code="1100")

customer = Customer.objects.create(
    entity=entity,
    name="Widget Corp",
    customer_code="WID-001",
    default_ar_account=ar_account,
)

print(f"Created customer: {customer.customer_code} - {customer.name}")
PY
```

Create and post an invoice:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Customer, Account, Entity, Invoice, InvoiceLine
from apps.accounting.services import post_invoice

entity = Entity.get_default()
customer = Customer.objects.get(customer_code="WID-001")
revenue_account = Account.objects.get(entity=entity, account_code="4000")

invoice = Invoice.objects.create(
    entity=entity,
    customer=customer,
    invoice_number="INV-001",
    date=date(2026, 5, 1),
    due_date=date(2026, 6, 1),
    total_amount=Decimal("1000.00"),
)

InvoiceLine.objects.create(
    invoice=invoice,
    account=revenue_account,
    line_description="Widget sale",
    amount=Decimal("1000.00"),
)

entry = post_invoice(invoice=invoice)

print(f"Posted invoice {invoice.invoice_number}")
print(f"Journal entry {entry.id}: {entry.status}")
print(f"Invoice status: {invoice.status}")
print(f"Outstanding balance: {invoice.outstanding_balance()}")
PY
```

Apply a payment to the invoice:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Customer, Account, Entity, Invoice, Payment
from apps.accounting.services import apply_payment_to_invoice

entity = Entity.get_default()
customer = Customer.objects.get(customer_code="WID-001")
invoice = Invoice.objects.get(invoice_number="INV-001")
cash_account = Account.objects.get(entity=entity, account_code="1000")  # Cash account

payment = Payment.objects.create(
    entity=entity,
    source_type=Payment.SourceType.INVOICE,
    source_id=invoice.id,
    amount=Decimal("600.00"),
    payment_date=date(2026, 5, 15),
    account=cash_account,
)

app, entry = apply_payment_to_invoice(
    payment=payment,
    invoice=invoice,
    applied_amount=Decimal("600.00"),
)

invoice.refresh_from_db()
print(f"Applied {app.applied_amount} to invoice")
print(f"Invoice status: {invoice.status}")
print(f"Outstanding balance: {invoice.outstanding_balance()}")
print(f"Journal entry {entry.id}: {entry.status}")
PY
```

Issue a customer credit:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from decimal import Decimal
from apps.accounting.models import Invoice
from apps.accounting.services import issue_customer_credit

invoice = Invoice.objects.get(invoice_number="INV-001")

credit, entry = issue_customer_credit(
    invoice=invoice,
    amount=Decimal("100.00"),
    reason="Return authorization",
)

invoice.refresh_from_db()
print(f"Issued credit of {credit.amount}")
print(f"Invoice status: {invoice.status}")
print(f"Outstanding balance: {invoice.outstanding_balance()}")
print(f"Journal entry {entry.id}: {entry.status}")
PY
```

View AR balance:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Account, Entity
from apps.accounting.selectors.balances import account_balance

entity = Entity.get_default()
ar = Account.objects.get(entity=entity, account_code="1100")  # Accounts Receivable

balance = account_balance(ar)
print(f"AR Account Balance: {balance}")
PY
```

Similar workflows apply to vendor bills and vendor payments.

## Run Tests

Use the project validation script:

```bash
./scripts/check.sh
```

Or run AR/AP tests specifically:

```bash
docker compose run --rm web pytest apps/accounting/tests/test_ar_ap_models.py -v
docker compose run --rm web pytest apps/accounting/tests/test_ar_ap_services.py -v
```

## Core Service Examples

### Create and post an invoice

```python
from datetime import date
from decimal import Decimal
from apps.accounting.models import Customer, Account, Entity, Invoice, InvoiceLine
from apps.accounting.services import post_invoice

entity = Entity.get_default()
customer = Customer.objects.get(customer_code="ACME-001")
revenue_account = Account.objects.get(entity=entity, account_code="4000")  # Revenue

invoice = Invoice.objects.create(
    entity=entity,
    customer=customer,
    invoice_number="INV-500",
    date=date(2026, 5, 15),
    due_date=date(2026, 6, 15),
    total_amount=Decimal("2500.00"),
)

InvoiceLine.objects.create(
    invoice=invoice,
    account=revenue_account,
    line_description="Professional services",
    amount=Decimal("2500.00"),
)

entry = post_invoice(invoice=invoice)
# Result: Debit AR 2500, Credit Revenue 2500
# Invoice status changes to POSTED
```

### Create and post a bill

```python
from datetime import date
from decimal import Decimal
from apps.accounting.models import Vendor, Account, Entity, Bill, BillLine
from apps.accounting.services import post_bill

entity = Entity.get_default()
vendor = Vendor.objects.get(vendor_code="SUPP-001")
expense_account = Account.objects.get(entity=entity, account_code="5000")  # Operating Expense

bill = Bill.objects.create(
    entity=entity,
    vendor=vendor,
    bill_number="BILL-300",
    date=date(2026, 5, 20),
    due_date=date(2026, 6, 20),
    total_amount=Decimal("1200.00"),
)

BillLine.objects.create(
    bill=bill,
    account=expense_account,
    line_description="Office supplies",
    amount=Decimal("1200.00"),
)

entry = post_bill(bill=bill)
# Result: Debit Expense 1200, Credit AP 1200
# Bill status changes to POSTED
```

### Apply a payment to an invoice

```python
from decimal import Decimal
from apps.accounting.models import Invoice, Payment
from apps.accounting.services import apply_payment_to_invoice

invoice = Invoice.objects.get(invoice_number="INV-500")
cash = Account.objects.get(account_code="1000")  # Cash

payment = Payment.objects.create(
    entity=invoice.entity,
    source_type=Payment.SourceType.INVOICE,
    source_id=invoice.id,
    amount=Decimal("2500.00"),
    payment_date=date(2026, 5, 25),
    account=cash,
)

app, entry = apply_payment_to_invoice(
    payment=payment,
    invoice=invoice,
    applied_amount=Decimal("2500.00"),
)
# Result: Debit Cash 2500, Credit AR 2500
# Invoice status changes to PAID
# Outstanding balance becomes 0
```

### Issue a customer credit

```python
from decimal import Decimal
from apps.accounting.models import Invoice
from apps.accounting.services import issue_customer_credit

invoice = Invoice.objects.get(invoice_number="INV-500")

credit, entry = issue_customer_credit(
    invoice=invoice,
    amount=Decimal("250.00"),
    reason="Quality adjustment",
)
# Result: Debit Revenue 250, Credit AR 250
# Creates PaymentApplication to reduce outstanding balance by 250
# Invoice status updated based on remaining balance
```

## Manual Acceptance Checks

1. Create a customer and configure a default AR account.
2. Create a vendor and configure a default AP account.
3. Create a draft invoice with revenue lines totaling $500.
4. Confirm the draft invoice does not affect AR balance.
5. Post the invoice and verify:
   - AR account is debited $500
   - Revenue account is credited $500
   - Invoice status changes to POSTED
   - Outstanding balance is $500
6. Apply a $300 payment to the invoice and verify:
   - Cash account is debited $300
   - AR account is credited $300
   - Invoice status changes to PARTIALLY_PAID
   - Outstanding balance is $200
7. Apply a $200 payment to close the invoice and verify:
   - Invoice status changes to PAID
   - Outstanding balance is $0
8. Create a draft bill with expense lines totaling $800.
9. Post the bill and verify:
   - Expense account is debited $800
   - AP account is credited $800
   - Bill status changes to POSTED
10. Issue a $100 credit to the bill and verify:
    - AP account is debited $100
    - Expense account is credited $100
    - Bill outstanding balance is reduced to $700
11. Attempt to post an invoice without a customer AR account and verify rejection with clear error message.
12. Verify audit logs record invoice posting, payment application, and credit issuance with metadata.

## Out-of-Scope Items

These behaviors are deferred to later epics or outside the AR/AP module:

- Invoice and bill voiding (reversal workflow similar to journal entries) — belongs to later refactoring
- Invoice aging reports — belongs to Epic 4: Reporting
- AP aging reports — belongs to Epic 4: Reporting
- Recurring invoices or payment schedules — belongs to future operational workflow epic
- Multi-currency invoice/bill support — belongs to later currency epic
- Tax code integration and tax calculation on invoices — belongs to Epic 4: Reporting/Tax
- Customer/vendor self-service portal — belongs to future customer-facing epic
- Automated payment matching/bank feeds — belongs to Epic 3: Banking
- Invoice numbering sequences with custom formats — belongs to future configuration epic
- Payment terms and due date calculations — belongs to future invoice workflow epic
- Dunning/collection management — belongs to future operational epic

## Accounting Rules Preserved

All AR/AP operations preserve the Epic 1 accounting invariants:

- Journal entries must balance (debits equal credits)
- Postings must belong to an open accounting period
- Posted entries are immutable except through reversal
- Reversed entries remain visible and offset the original
- Balance calculations exclude draft entries
- Audit logs record all successful accounting actions
- AR/AP balances are calculated from GL, not stored state
