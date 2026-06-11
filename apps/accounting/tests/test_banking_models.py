from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account, BankAccount, Entity


@pytest.fixture
def entity():
    return Entity.get_default()


@pytest.fixture
def bank_ledger_account(entity):
    return Account.objects.create(
        entity=entity,
        account_code="1000",
        name="Cash",
        type=Account.AccountType.ASSET,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.mark.django_db
class TestBankAccount:
    def test_create_multiple_bank_accounts_per_entity(self, entity, bank_ledger_account):
        first = BankAccount.objects.create(
            entity=entity,
            name="Operating Checking",
            account_number="1111",
            bank_name="First Bank",
            ledger_account=bank_ledger_account,
        )
        second = BankAccount.objects.create(
            entity=entity,
            name="Payroll Checking",
            account_number="2222",
            bank_name="First Bank",
            ledger_account=bank_ledger_account,
        )

        assert first.entity == entity
        assert second.entity == entity
        assert first.account_number != second.account_number
        assert first.current_balance() == Decimal("0.00")
        assert second.current_balance() == Decimal("0.00")

    def test_bank_account_clean_rejects_other_entity_ledger_account(self, entity, bank_ledger_account):
        other_entity = Entity.objects.create(name="Other", slug="other")
        other_ledger = Account.objects.create(
            entity=other_entity,
            account_code="1000",
            name="Cash",
            type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT,
        )

        bank_account = BankAccount(
            entity=entity,
            name="Operating Checking",
            account_number="1111",
            bank_name="First Bank",
            ledger_account=other_ledger,
        )

        with pytest.raises(ValidationError):
            bank_account.clean()

    def test_bank_account_clean_rejects_non_cash_ledger_account(self, entity):
        expense_account = Account.objects.create(
            entity=entity,
            account_code="5000",
            name="Expense",
            type=Account.AccountType.EXPENSE,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        bank_account = BankAccount(
            entity=entity,
            name="Operating Checking",
            account_number="1111",
            bank_name="First Bank",
            ledger_account=expense_account,
        )

        with pytest.raises(ValidationError):
            bank_account.clean()
