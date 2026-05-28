from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum

from apps.accounting.models import Account, Entity, JournalEntry, JournalLine
from apps.accounting.services.entities import get_default_entity

ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


def money_amount(value: Decimal | None) -> Decimal:
    return (value or ZERO).quantize(MONEY_QUANT)


def normal_balance_amount(*, normal_balance: str, debits: Decimal, credits: Decimal) -> Decimal:
    if normal_balance == Account.NormalBalance.DEBIT:
        return money_amount(debits - credits)
    return money_amount(credits - debits)


def posted_line_totals(account: Account) -> tuple[Decimal, Decimal]:
    """Return posted debit and credit totals for one account.

    Draft entries do not affect balances. Reversed originals remain part of the
    historical ledger, and their posted reversing entries offset them.
    """

    aggregates = account.lines.filter(
        journal_entry__status__in=JournalEntry.ledger_affecting_statuses()
    ).aggregate(
        debits=Sum("amount", filter=Q(side=JournalLine.Side.DEBIT)),
        credits=Sum("amount", filter=Q(side=JournalLine.Side.CREDIT)),
    )
    return money_amount(aggregates["debits"]), money_amount(aggregates["credits"])


def account_balance(account: Account) -> Decimal:
    debits, credits = posted_line_totals(account)
    return normal_balance_amount(
        normal_balance=account.normal_balance,
        debits=debits,
        credits=credits,
    )


def trial_balance(entity: Entity | None = None) -> list[dict[str, str]]:
    """Return active account balances for the default/entity chart of accounts.

    The selector owns read-model/reporting balance math. It intentionally uses
    posted ledger-affecting statuses only, so draft entries are excluded and
    reversals offset the entries they reverse.
    """

    entity = entity or get_default_entity()
    accounts = Account.objects.filter(entity=entity, is_active=True).annotate(
        posted_debits=Sum(
            "lines__amount",
            filter=Q(
                lines__side=JournalLine.Side.DEBIT,
                lines__journal_entry__status__in=JournalEntry.ledger_affecting_statuses(),
            ),
        ),
        posted_credits=Sum(
            "lines__amount",
            filter=Q(
                lines__side=JournalLine.Side.CREDIT,
                lines__journal_entry__status__in=JournalEntry.ledger_affecting_statuses(),
            ),
        ),
    ).order_by("account_code")

    rows = []
    for account in accounts:
        debits = money_amount(account.posted_debits)
        credits = money_amount(account.posted_credits)
        balance = normal_balance_amount(
            normal_balance=account.normal_balance,
            debits=debits,
            credits=credits,
        )
        rows.append(
            {
                "account_code": account.account_code,
                "name": account.name,
                "type": account.type,
                "normal_balance": account.normal_balance,
                "balance": str(balance),
            }
        )
    return rows
