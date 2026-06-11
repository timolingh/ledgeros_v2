from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.accounting.models import BankAccount, BankTransaction

ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


def money_amount(value: Decimal | None) -> Decimal:
    return (value or ZERO).quantize(MONEY_QUANT)


def bank_account_balance(bank_account: BankAccount, as_of: date | None = None) -> Decimal:
    transactions = bank_account.transactions.all()
    if as_of is not None:
        transactions = transactions.filter(transaction_date__lte=as_of)

    aggregates = transactions.aggregate(
        deposits=Sum("amount", filter=Q(transaction_type=BankTransaction.Type.DEPOSIT)),
        withdrawals=Sum("amount", filter=Q(transaction_type=BankTransaction.Type.WITHDRAWAL)),
    )
    return money_amount(aggregates["deposits"]) - money_amount(aggregates["withdrawals"])
