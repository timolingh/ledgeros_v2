# LedgerOS Epic 3 Banking and Reconciliation Implementation

This document describes the Banking and Reconciliation implementation for LedgerOS, building on the foundational accounting core from Epic 1 and the AR/AP workflows from Epic 2.

## Scope Implemented

- Bank account records linked to GL accounts
- Multiple bank accounts per entity
- Bank transaction recording for deposits and withdrawals
- Bank statement line capture
- Bank reconciliation records and match records
- Bank balance selector for read-model balance calculations
- Service-layer architecture preserving accounting invariants
- Admin surfaces for bank account setup and read-only banking records
- Unit and integration tests for banking workflows
- Dockerized runtime for local development, testing, and deployment

## Structure

```text
apps/accounting/
  models/
    banking.py                  # Bank accounts, transactions, statement lines, reconciliations
  services/
    banking.py                  # Bank account setup, transaction posting, reconciliation workflow
  selectors/
    banking.py                  # Bank account balance selector
  tests/
    test_banking_models.py      # Model validation and constraint tests
    test_banking_services.py    # Service-layer integration tests
  migrations/
    0005_bankaccount_...        # Banking model schema
```

## Explicit Domain Assumptions

- MVP uses one hidden default entity; bank accounts belong to that entity.
- Each entity may manage multiple bank accounts.
- Each bank account must link to a debit-normal asset account in the same entity.
- Bank transactions post through the linked ledger account.
- Deposits increase the bank balance; withdrawals decrease it.
- Reconciliation is per bank account, not per entity-wide cash pool.
- Statement lines and bank transactions must stay matched one-to-one for the MVP reconciliation workflow.
- Reconciliations remain open until statement lines are matched and the statement ending balance agrees with book balance.
- All banking state changes go through the service layer and create audit logs.
- Bank account balances are calculated from posted bank transactions, not stored as denormalized totals.

## Local Run

Starting from a running Docker environment with Epic 1 core and Epic 2 AR/AP:

```bash
# Apply migrations
docker compose run --rm web python manage.py migrate

# Optional: import the sample chart of accounts if you want to create bank accounts against seeded GL accounts
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml

# Create an accounting period (required for posting bank transactions)
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

# Create two cash accounts and two bank accounts for the same entity
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Account, BankAccount, Entity

entity = Entity.get_default()
cash = Account.objects.get(entity=entity, account_code="1000")

first_bank = BankAccount.objects.create(
    entity=entity,
    name="Operating Checking",
    account_number="1111",
    bank_name="First Bank",
    ledger_account=cash,
)

second_bank = BankAccount.objects.create(
    entity=entity,
    name="Payroll Checking",
    account_number="2222",
    bank_name="Second Bank",
    ledger_account=cash,
)

print(f"Created bank accounts: {first_bank.name}, {second_bank.name}")
PY
```

Record a bank deposit:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, Entity, BankTransaction
from apps.accounting.services.banking import record_bank_transaction

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="1111")
revenue_account = Account.objects.get(entity=entity, account_code="4000")

transaction = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 1),
    amount=Decimal("250.00"),
    transaction_type=BankTransaction.Type.DEPOSIT,
    offset_account=revenue_account,
    memo="Customer deposit",
)

print(f"Recorded transaction {transaction.id}")
print(f"Type: {transaction.transaction_type}")
print(f"Bank balance: {bank_account.current_balance()}")
PY
```

Record a bank withdrawal:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, Entity, BankTransaction
from apps.accounting.services.banking import record_bank_transaction

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="2222")
expense_account = Account.objects.get(entity=entity, account_code="5000")

transaction = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 2),
    amount=Decimal("40.00"),
    transaction_type=BankTransaction.Type.WITHDRAWAL,
    offset_account=expense_account,
    memo="Bank fee",
)

print(f"Recorded transaction {transaction.id}")
print(f"Type: {transaction.transaction_type}")
print(f"Bank balance: {bank_account.current_balance()}")
PY
```

Create and complete a reconciliation:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, BankTransaction, Entity
from apps.accounting.services.banking import (
    complete_bank_reconciliation,
    create_bank_reconciliation,
    create_bank_statement_line,
    match_bank_statement_line,
    record_bank_transaction,
)

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="1111")
revenue_account = Account.objects.get(entity=entity, account_code="4000")

deposit = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 1),
    amount=Decimal("150.00"),
    transaction_type=BankTransaction.Type.DEPOSIT,
    offset_account=revenue_account,
    memo="Deposit",
)

statement_line = create_bank_statement_line(
    bank_account=bank_account,
    statement_date=date(2026, 5, 1),
    amount=Decimal("150.00"),
    description="Deposit",
    statement_reference="STMT-1",
)

reconciliation = create_bank_reconciliation(
    bank_account=bank_account,
    start_date=date(2026, 5, 1),
    end_date=date(2026, 5, 1),
    statement_ending_balance=Decimal("150.00"),
)

match_bank_statement_line(
    reconciliation=reconciliation,
    statement_line=statement_line,
    bank_transaction=deposit,
)

completed = complete_bank_reconciliation(reconciliation=reconciliation)

print(f"Reconciliation status: {completed.status}")
print(f"Cleared balance: {completed.cleared_balance}")
PY
```

## Run Tests

Use the project validation script:

```bash
./scripts/check.sh
```

Or run the Epic 3 banking tests specifically:

```bash
docker compose run --rm web pytest apps/accounting/tests/test_banking_models.py -v
docker compose run --rm web pytest apps/accounting/tests/test_banking_services.py -v
```

## Core Service Examples

### Create a bank account

```python
from apps.accounting.models import Account, BankAccount, Entity
from apps.accounting.services.banking import save_bank_account

entity = Entity.get_default()
cash_account = Account.objects.get(entity=entity, account_code="1000")

bank_account = save_bank_account(
    entity=entity,
    name="Operating Checking",
    account_number="1111",
    bank_name="First Bank",
    ledger_account=cash_account,
)
```

### Record a deposit

```python
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, BankTransaction, Entity
from apps.accounting.services.banking import record_bank_transaction

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="1111")
revenue_account = Account.objects.get(entity=entity, account_code="4000")

transaction = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 1),
    amount=Decimal("250.00"),
    transaction_type=BankTransaction.Type.DEPOSIT,
    offset_account=revenue_account,
    memo="Customer deposit",
)
```

### Record a withdrawal

```python
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, BankTransaction, Entity
from apps.accounting.services.banking import record_bank_transaction

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="2222")
expense_account = Account.objects.get(entity=entity, account_code="5000")

transaction = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 2),
    amount=Decimal("40.00"),
    transaction_type=BankTransaction.Type.WITHDRAWAL,
    offset_account=expense_account,
    memo="Bank fee",
)
```

### Create and complete a reconciliation

```python
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, BankAccount, BankTransaction, Entity
from apps.accounting.services.banking import (
    complete_bank_reconciliation,
    create_bank_reconciliation,
    create_bank_statement_line,
    match_bank_statement_line,
    record_bank_transaction,
)

entity = Entity.get_default()
bank_account = BankAccount.objects.get(entity=entity, account_number="1111")
revenue_account = Account.objects.get(entity=entity, account_code="4000")

deposit = record_bank_transaction(
    bank_account=bank_account,
    transaction_date=date(2026, 5, 1),
    amount=Decimal("150.00"),
    transaction_type=BankTransaction.Type.DEPOSIT,
    offset_account=revenue_account,
    memo="Deposit",
)

statement_line = create_bank_statement_line(
    bank_account=bank_account,
    statement_date=date(2026, 5, 1),
    amount=Decimal("150.00"),
    description="Deposit",
    statement_reference="STMT-1",
)

reconciliation = create_bank_reconciliation(
    bank_account=bank_account,
    start_date=date(2026, 5, 1),
    end_date=date(2026, 5, 1),
    statement_ending_balance=Decimal("150.00"),
)

match_bank_statement_line(
    reconciliation=reconciliation,
    statement_line=statement_line,
    bank_transaction=deposit,
)

complete_bank_reconciliation(reconciliation=reconciliation)
```

## Manual Acceptance Checks

1. Create a cash GL account for the default entity.
2. Create two bank accounts for the same entity.
3. Verify each bank account links to a debit-normal asset account.
4. Record a deposit on one bank account and confirm only that account balance changes.
5. Record a withdrawal on the other bank account and confirm balances remain independent.
6. Import or create statement lines for a reconciliation period.
7. Match statement lines to bank transactions and verify duplicates are rejected.
8. Complete the reconciliation and verify the status becomes `completed`.
9. Confirm audit logs exist for bank account creation, bank transaction posting, statement line creation, and reconciliation completion.

## Out-of-Scope Items

These behaviors are deferred to later epics or outside the Epic 3 banking module:

- Full bank-feed integrations and bank API authentication
- Automated matching rules beyond the MVP one-to-one reconciliation workflow
- Bank transfer workflows between bank accounts
- Advanced bank import parsers for institution-specific statement formats
- Cash forecasting and treasury management
- UI screens for the banking workspace
