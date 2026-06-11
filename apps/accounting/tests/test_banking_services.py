from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account, BankAccount, BankReconciliation, BankTransaction, JournalEntry
from apps.accounting.selectors import account_balance, bank_account_balance
from apps.accounting.services import create_accounting_period
from apps.accounting.services import get_or_create_undeposited_funds_account
from apps.accounting.services.banking import (
    complete_bank_reconciliation,
    create_bank_reconciliation,
    create_bank_statement_line,
    match_bank_statement_line,
    record_bank_transaction,
)
from apps.accounting.services.entities import get_default_entity


@pytest.fixture
def entity():
    return get_default_entity()


@pytest.fixture
def period():
    return create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")


@pytest.fixture
def cash_account(entity):
    return Account.objects.create(
        entity=entity,
        account_code="1000",
        name="Cash",
        type=Account.AccountType.ASSET,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.fixture
def undeposited_funds_account(entity):
    return get_or_create_undeposited_funds_account(entity=entity)


@pytest.fixture
def revenue_account(entity):
    return Account.objects.create(
        entity=entity,
        account_code="4000",
        name="Revenue",
        type=Account.AccountType.REVENUE,
        normal_balance=Account.NormalBalance.CREDIT,
    )


@pytest.fixture
def expense_account(entity):
    return Account.objects.create(
        entity=entity,
        account_code="5000",
        name="Expense",
        type=Account.AccountType.EXPENSE,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.fixture
def bank_account(entity, cash_account):
    return BankAccount.objects.create(
        entity=entity,
        name="Operating Checking",
        account_number="1111",
        bank_name="First Bank",
        ledger_account=cash_account,
    )


@pytest.fixture
def second_bank_account(entity, cash_account):
    return BankAccount.objects.create(
        entity=entity,
        name="Payroll Checking",
        account_number="2222",
        bank_name="Second Bank",
        ledger_account=cash_account,
    )


@pytest.mark.django_db
class TestBankTransactions:
    def test_record_deposit_posts_to_bank_account(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("125.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Customer deposit",
        )

        bank_account.refresh_from_db()
        assert bank_transaction.transaction_type == BankTransaction.Type.DEPOSIT
        assert bank_account_balance(bank_account) == Decimal("125.00")
        assert account_balance(bank_account.ledger_account) == Decimal("125.00")

        entry = bank_transaction.journal_entry
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.lines.filter(account=bank_account.ledger_account, side="debit").count() == 1
        assert entry.lines.filter(account=revenue_account, side="credit").count() == 1

    def test_record_deposit_can_clear_undeposited_funds(self, bank_account, undeposited_funds_account, period):
        record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("125.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=undeposited_funds_account,
            memo="Deposit from clearing",
        )

        assert bank_account_balance(bank_account) == Decimal("125.00")
        assert account_balance(undeposited_funds_account) == Decimal("-125.00")

    def test_record_withdrawal_posts_to_second_bank_account_independently(self, bank_account, second_bank_account, expense_account, period):
        record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("100.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=expense_account,
            memo="Opening deposit",
        )
        record_bank_transaction(
            bank_account=second_bank_account,
            transaction_date=date(2026, 5, 2),
            amount=Decimal("40.00"),
            transaction_type=BankTransaction.Type.WITHDRAWAL,
            offset_account=expense_account,
            memo="Bank fee",
        )

        assert bank_account_balance(bank_account) == Decimal("100.00")
        assert bank_account_balance(second_bank_account) == Decimal("-40.00")


@pytest.mark.django_db
class TestBankReconciliation:
    def test_reconciliation_completes_when_matches_and_balance_align(self, bank_account, revenue_account, expense_account, period):
        deposit = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("150.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        withdrawal = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 2),
            amount=Decimal("50.00"),
            transaction_type=BankTransaction.Type.WITHDRAWAL,
            offset_account=expense_account,
            memo="Fee",
        )

        statement_one = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("150.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        statement_two = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 2),
            amount=Decimal("-50.00"),
            description="Fee",
            statement_reference="STMT-2",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
            statement_ending_balance=Decimal("100.00"),
        )

        match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_one, bank_transaction=deposit)
        match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_two, bank_transaction=withdrawal)

        completed = complete_bank_reconciliation(reconciliation=reconciliation)

        completed.refresh_from_db()
        expected_cleared = sum(
            (match.bank_transaction.signed_amount for match in completed.matches.select_related("bank_transaction")),
            Decimal("0.00"),
        )
        assert completed.status == BankReconciliation.Status.COMPLETED
        assert completed.cleared_balance == expected_cleared
        assert completed.cleared_balance == Decimal("100.00")

    def test_reconciliation_rejects_duplicate_matching(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

        with pytest.raises(ValidationError):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_deposit_with_negative_statement_amount(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("-25.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        with pytest.raises(ValidationError, match="positive statement line amount"):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_withdrawal_with_positive_statement_amount(self, bank_account, expense_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.WITHDRAWAL,
            offset_account=expense_account,
            memo="Withdrawal",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            description="Withdrawal",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("-25.00"),
        )

        with pytest.raises(ValidationError, match="negative statement line amount"):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_mismatched_transaction_amount(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("30.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        with pytest.raises(ValidationError, match="Statement line amount must match the bank transaction signed amount"):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_statement_line_outside_period(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 2),
            amount=Decimal("25.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        with pytest.raises(ValidationError, match="Statement line date must fall within the reconciliation period"):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_transaction_outside_period(self, bank_account, revenue_account, period):
        bank_transaction = record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 2),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        statement_line = create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        with pytest.raises(ValidationError, match="Bank transaction date must fall within the reconciliation period"):
            match_bank_statement_line(reconciliation=reconciliation, statement_line=statement_line, bank_transaction=bank_transaction)

    def test_reconciliation_rejects_unmatched_statement_lines(self, bank_account, revenue_account, period):
        record_bank_transaction(
            bank_account=bank_account,
            transaction_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Type.DEPOSIT,
            offset_account=revenue_account,
            memo="Deposit",
        )
        create_bank_statement_line(
            bank_account=bank_account,
            statement_date=date(2026, 5, 1),
            amount=Decimal("25.00"),
            description="Deposit",
            statement_reference="STMT-1",
        )
        reconciliation = create_bank_reconciliation(
            bank_account=bank_account,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
            statement_ending_balance=Decimal("25.00"),
        )

        with pytest.raises(ValidationError):
            complete_bank_reconciliation(reconciliation=reconciliation)
