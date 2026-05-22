from __future__ import annotations

from decimal import Decimal

from apps.accounting.models import Account, Entity
from apps.accounting.services.entities import get_default_entity


def account_balance(account: Account) -> Decimal:
    return account.posted_balance()


def trial_balance(entity: Entity | None = None) -> list[dict[str, str]]:
    entity = entity or get_default_entity()
    rows = []
    for account in Account.objects.filter(entity=entity, is_active=True).order_by("account_code"):
        balance = account.posted_balance()
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
