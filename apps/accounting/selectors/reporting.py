from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.accounting.models import Account, Entity, JournalEntry, JournalLine
from apps.accounting.selectors.balances import money_amount, normal_balance_amount
from apps.accounting.services.entities import get_default_entity


def posted_line_totals_as_of(account: Account, as_of: date | None = None) -> tuple[Decimal, Decimal]:
    queryset = account.lines.filter(journal_entry__status__in=JournalEntry.ledger_affecting_statuses())
    if as_of is not None:
        queryset = queryset.filter(journal_entry__date__lte=as_of)
    aggregates = queryset.aggregate(
        debits=Sum("amount", filter=Q(side=JournalLine.Side.DEBIT)),
        credits=Sum("amount", filter=Q(side=JournalLine.Side.CREDIT)),
    )
    return money_amount(aggregates["debits"]), money_amount(aggregates["credits"])


def account_balance_as_of(account: Account, as_of: date | None = None) -> Decimal:
    debits, credits = posted_line_totals_as_of(account, as_of=as_of)
    return normal_balance_amount(normal_balance=account.normal_balance, debits=debits, credits=credits)


def trial_balance_as_of(entity: Entity | None = None, as_of: date | None = None) -> list[dict[str, str]]:
    entity = entity or get_default_entity()
    accounts = Account.objects.filter(entity=entity, is_active=True).order_by("account_code")
    rows: list[dict[str, str]] = []
    for account in accounts:
        debits, credits = posted_line_totals_as_of(account, as_of=as_of)
        balance = normal_balance_amount(normal_balance=account.normal_balance, debits=debits, credits=credits)
        rows.append(
            {
                "account_code": account.account_code,
                "name": account.name,
                "type": account.type,
                "normal_balance": account.normal_balance,
                "debits": str(debits),
                "credits": str(credits),
                "balance": str(balance),
            }
        )
    return rows
