from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import Account, AccountingPeriod, Entity
from apps.accounting.services.entities import get_default_entity


@transaction.atomic
def save_account(*, account: Account | None = None, entity: Entity | None = None, account_code: str, name: str, type: str, normal_balance: str, is_active: bool = True) -> Account:
    entity = entity or get_default_entity()
    if account is None:
        account = Account(entity=entity, account_code=account_code, name=name, type=type, normal_balance=normal_balance, is_active=is_active)
    else:
        account.account_code = account_code
        account.name = name
        account.type = type
        account.normal_balance = normal_balance
        account.is_active = is_active
        if not account.entity_id:
            account.entity = entity
    account.full_clean()
    account.save()
    return account


def _assert_period_dates_are_valid(*, period: AccountingPeriod | None, entity: Entity, start_date: date, end_date: date) -> None:
    query = AccountingPeriod.objects.filter(entity=entity, start_date__lte=end_date, end_date__gte=start_date)
    if period is not None and period.pk is not None:
        query = query.exclude(pk=period.pk)
    if query.exists():
        raise ValidationError("Accounting periods may not overlap for the default entity.")


@transaction.atomic
def save_accounting_period(*, period: AccountingPeriod | None = None, start_date: date, end_date: date, name: str = "", entity: Entity | None = None) -> AccountingPeriod:
    entity = entity or get_default_entity()
    _assert_period_dates_are_valid(period=period, entity=entity, start_date=start_date, end_date=end_date)
    if period is None:
        period = AccountingPeriod(entity=entity, start_date=start_date, end_date=end_date, name=name)
    else:
        period.start_date = start_date
        period.end_date = end_date
        period.name = name
        if not period.entity_id:
            period.entity = entity
    period.full_clean()
    period.save()
    return period
